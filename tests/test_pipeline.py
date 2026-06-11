"""
test_pipeline.py — pytest suite for the Mindex data pipeline.

Run: pytest tests/ -v

TDD workflow: tests are written before implementations.
Each test will fail with NotImplementedError until the corresponding
src/ module is implemented.

Sections:
  - Profiler (Part 1)
  - Cleaner (Part 2)
  - Analytics (Part 4)
"""
import sqlite3
import pytest
import pandas as pd
import sys
from pathlib import Path

# Allow imports from src/ when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from profiler import profile
from cleaner import normalize_dates, strip_dollar, clean_stores, clean_products, clean_transactions


# ── Profiler tests ────────────────────────────────────────────────────────────

class TestProfiler:

    def test_empty_dataframe(self):
        """profile() must handle a zero-row DataFrame without error."""
        df = pd.DataFrame({"a": pd.Series([], dtype=float), "b": pd.Series([], dtype=str)})
        result = profile(df, "empty")
        assert result["row_count"] == 0
        assert result["col_count"] == 2
        assert result["duplicate_row_count"] == 0

    def test_all_null_column(self):
        """A column that is entirely null should report 100% null."""
        df = pd.DataFrame({"a": [None, None, None], "b": [1, 2, 3]})
        result = profile(df, "nulls")
        assert result["columns"]["a"]["null_pct"] == 100.0
        assert result["columns"]["b"]["null_count"] == 0

    def test_numeric_stats(self):
        """Numeric columns must include zero_count and negative_count."""
        df = pd.DataFrame({"val": [-5.0, 0.0, 0.0, 10.0, 20.0]})
        result = profile(df, "nums")
        col = result["columns"]["val"]
        assert col["zero_count"] == 2
        assert col["negative_count"] == 1
        assert col["min"] == -5.0
        assert col["max"] == 20.0

    def test_future_date_detection(self):
        """Date-like string column should report future_date_count."""
        df = pd.DataFrame({"txn_date": ["2020-01-01", "2099-12-31", "2021-06-15"]})
        result = profile(df, "dates")
        col = result["columns"]["txn_date"]
        assert "future_date_count" in col
        assert col["future_date_count"] == 1

    def test_duplicate_row_count(self):
        """Exact duplicate rows must be counted."""
        df = pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]})
        result = profile(df, "dups")
        assert result["duplicate_row_count"] == 1


# ── Cleaner tests ─────────────────────────────────────────────────────────────

class TestCleaner:

    def test_normalize_dates_iso(self):
        """ISO dates should pass through unchanged."""
        df = pd.DataFrame({"d": ["2026-01-15", "2026-03-22"]})
        result = normalize_dates(df, "d")
        assert list(result["d"]) == ["2026-01-15", "2026-03-22"]

    def test_normalize_dates_us_format(self):
        """MM/DD/YYYY should be converted to YYYY-MM-DD."""
        df = pd.DataFrame({"d": ["01/15/2026", "03/22/2026"]})
        result = normalize_dates(df, "d")
        assert list(result["d"]) == ["2026-01-15", "2026-03-22"]

    def test_normalize_dates_eu_format(self):
        """DD-MM-YYYY should be converted to YYYY-MM-DD."""
        df = pd.DataFrame({"d": ["15-01-2026", "22-03-2026"]})
        result = normalize_dates(df, "d")
        assert list(result["d"]) == ["2026-01-15", "2026-03-22"]

    def test_normalize_dates_mixed(self):
        """Mixed formats in the same column should all normalize correctly."""
        df = pd.DataFrame({"d": ["2026-01-15", "01/15/2026", "15-01-2026"]})
        result = normalize_dates(df, "d")
        assert list(result["d"]) == ["2026-01-15", "2026-01-15", "2026-01-15"]

    def test_strip_dollar_returns_float(self):
        """$-prefixed strings should become floats."""
        df = pd.DataFrame({"amt": ["$12.50", "$0.99", "$249.00"]})
        result = strip_dollar(df, "amt")
        assert result["amt"].dtype == float
        assert result["amt"].iloc[0] == pytest.approx(12.50)

    def test_strip_dollar_already_numeric(self):
        """Values without $ prefix should also be handled (mixed column)."""
        df = pd.DataFrame({"amt": ["$12.50", "25.00", "$3.99"]})
        result = strip_dollar(df, "amt")
        assert result["amt"].dtype == float
        assert result["amt"].iloc[1] == pytest.approx(25.00)


# ── Cleaner — entity-level data quality tests ────────────────────────────────

class TestCleanerDataQuality:
    """Tests that verify each documented DQ decision in the data quality table."""

    # --- clean_stores ---

    def test_stores_near_dup_keeps_first(self):
        """S007-style: same store_id, different names → keep first row."""
        df = pd.DataFrame([
            {"store_id": "S007", "store_name": "Store A",         "zip_code": "12345", "region": "NE", "city": None, "state": None, "opened_date": None},
            {"store_id": "S007", "store_name": "Store A Renamed", "zip_code": "12345", "region": "NE", "city": None, "state": None, "opened_date": None},
        ])
        result = clean_stores(df)
        assert len(result) == 1
        assert result.iloc[0]["store_name"] == "Store A"

    def test_stores_malformed_zip_kept_with_flag(self):
        """S003-style: 4-digit zip → row kept, zip_valid=0, original value preserved."""
        df = pd.DataFrame([{"store_id": "S003", "store_name": "Bad Zip", "zip_code": "0938", "region": "South", "city": None, "state": None, "opened_date": None}])
        result = clean_stores(df)
        assert len(result) == 1
        assert result.iloc[0]["zip_valid"] == 0
        assert result.iloc[0]["zip_code"] == "0938"

    def test_stores_null_region_becomes_unknown(self):
        """S013/S014-style: NULL region → 'Unknown'."""
        df = pd.DataFrame([{"store_id": "S013", "store_name": "Portland", "zip_code": "97201", "region": None, "city": None, "state": None, "opened_date": None}])
        result = clean_stores(df)
        assert result.iloc[0]["region"] == "Unknown"

    # --- clean_products ---

    def test_products_exact_dup_removed(self):
        """P012-style: exact duplicate row → deduplicated to one, correct row kept."""
        row = {"product_id": "P012", "product_name": "Widget", "category": "Tools", "unit_price": 9.99, "supplier_id": "SUP1"}
        result = clean_products(pd.DataFrame([row, row]))
        assert len(result) == 1
        assert result.iloc[0]["product_id"] == "P012"
        assert result.iloc[0]["unit_price"] == pytest.approx(9.99)

    def test_products_price_conflict_keeps_last(self):
        """P005-style: same product_id, two prices → keep last (latest catalog price)."""
        df = pd.DataFrame([
            {"product_id": "P005", "product_name": "Gadget", "category": "Electronics", "unit_price": 49.99, "supplier_id": "SUP1"},
            {"product_id": "P005", "product_name": "Gadget", "category": "Electronics", "unit_price": 59.99, "supplier_id": "SUP1"},
        ])
        result = clean_products(df)
        assert len(result) == 1
        assert result.iloc[0]["unit_price"] == pytest.approx(59.99)

    def test_products_null_category_becomes_uncategorized(self):
        """P003-style: NULL category → 'Uncategorized'."""
        df = pd.DataFrame([{"product_id": "P003", "product_name": "Mystery", "category": None, "unit_price": 5.00, "supplier_id": "SUP1"}])
        result = clean_products(df)
        assert result.iloc[0]["category"] == "Uncategorized"

    def test_products_zero_price_kept_with_flag(self):
        """P027-style: zero unit_price → row kept, price_is_zero=1, price value preserved."""
        df = pd.DataFrame([{"product_id": "P027", "product_name": "Free Item", "category": "Promo", "unit_price": 0.0, "supplier_id": "SUP1"}])
        result = clean_products(df)
        assert len(result) == 1
        assert result.iloc[0]["price_is_zero"] == 1
        assert result.iloc[0]["unit_price"] == pytest.approx(0.0)

    # --- clean_transactions ---

    def test_transactions_orphaned_store_excluded(self):
        """S016-S019-style: store_id not in valid set → excluded with reason logged."""
        df = pd.DataFrame([
            {"transaction_id": "T1", "store_id": "S001", "product_id": "P001", "customer_id": "C1",
             "transaction_date": "2026-03-01", "quantity": 1, "unit_price": 10.0, "total_amount": 10.0},
            {"transaction_id": "T2", "store_id": "S999", "product_id": "P001", "customer_id": "C1",
             "transaction_date": "2026-03-01", "quantity": 1, "unit_price": 10.0, "total_amount": 10.0},
        ])
        result, excl = clean_transactions(df, {"S001"}, {"P001"})
        assert len(result) == 1
        assert result.iloc[0]["transaction_id"] == "T1"
        assert "T2" not in result["transaction_id"].values
        assert any("orphaned_store_id" in e["reason"] for e in excl)

    def test_transactions_null_customer_becomes_guest(self):
        """NULL customer_id → mapped to synthetic 'CUST_GUEST', row kept."""
        df = pd.DataFrame([{
            "transaction_id": "T1", "store_id": "S001", "product_id": "P001",
            "customer_id": None, "transaction_date": "2026-03-01",
            "quantity": 1, "unit_price": 10.0, "total_amount": 10.0,
        }])
        result, _ = clean_transactions(df, {"S001"}, {"P001"})
        assert len(result) == 1
        assert result.iloc[0]["customer_id"] == "CUST_GUEST"

    def test_transactions_return_flagged_and_kept(self):
        """Negative quantity → is_return=1, row included in output."""
        df = pd.DataFrame([{
            "transaction_id": "T1", "store_id": "S001", "product_id": "P001",
            "customer_id": "C1", "transaction_date": "2026-03-01",
            "quantity": -2, "unit_price": 10.0, "total_amount": -20.0,
        }])
        result, excl = clean_transactions(df, {"S001"}, {"P001"})
        assert len(result) == 1
        assert result.iloc[0]["is_return"] == 1
        assert len(excl) == 0  # returns are kept, not excluded


# ── Analytics tests ───────────────────────────────────────────────────────────

class TestAnalytics:

    @pytest.fixture
    def mem_db(self):
        """In-memory SQLite with a small controlled fixture for query testing."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE dim_date (
                date_key INTEGER PRIMARY KEY,
                full_date TEXT,
                year INTEGER,
                month INTEGER,
                day INTEGER
            );
            CREATE TABLE dim_store (
                store_key INTEGER PRIMARY KEY,
                store_id TEXT,
                store_name TEXT,
                region TEXT
            );
            CREATE TABLE dim_product (
                product_key INTEGER PRIMARY KEY,
                product_id TEXT,
                category TEXT,
                unit_price REAL
            );
            CREATE TABLE dim_customer (
                customer_key INTEGER PRIMARY KEY,
                customer_id TEXT,
                is_guest INTEGER DEFAULT 0
            );
            CREATE TABLE fact_sales (
                transaction_id TEXT PRIMARY KEY,
                date_key INTEGER,
                store_key INTEGER,
                product_key INTEGER,
                customer_key INTEGER,
                quantity INTEGER,
                unit_price REAL,
                total_amount REAL,
                is_return INTEGER DEFAULT 0,
                has_price_discrepancy INTEGER DEFAULT 0
            );
        """)
        # Dates: 20260601 is within last 30 days of 20260602 (max date in data)
        conn.executemany("INSERT INTO dim_date VALUES (?,?,?,?,?)", [
            (20260601, "2026-06-01", 2026, 6, 1),
            (20260501, "2026-05-01", 2026, 5, 1),
        ])
        conn.executemany("INSERT INTO dim_store VALUES (?,?,?,?)", [
            (1, "S001", "Store A", "Northeast"),
            (2, "S002", "Store B", "Midwest"),
        ])
        conn.executemany("INSERT INTO dim_product VALUES (?,?,?,?)", [
            (1, "P001", "Electronics", 99.99),
            (2, "P002", "Apparel",     29.99),
        ])
        conn.executemany("INSERT INTO dim_customer VALUES (?,?,?)", [
            (1, "CUST0001", 0),
            (2, "CUST0002", 0),
            (3, "CUST_GUEST", 1),
        ])
        conn.executemany(
            "INSERT INTO fact_sales VALUES (?,?,?,?,?,?,?,?,?,?)", [
            # Store A: 300 + 100 = 400 net revenue in June
            ("TXN001", 20260601, 1, 1, 1, 3, 99.99, 300.00, 0, 0),
            ("TXN002", 20260601, 1, 2, 2, 4, 25.00, 100.00, 0, 0),
            # Store B: 50 - 20 = 30 net revenue in June (has a return)
            ("TXN003", 20260601, 2, 1, 1, 1, 50.00,  50.00, 0, 0),
            ("TXN004", 20260601, 2, 1, 3, -1, 20.00, -20.00, 1, 0),
            # May transaction (outside 30-day window)
            ("TXN005", 20260501, 1, 2, 2, 2, 29.99,  59.98, 0, 0),
        ])
        conn.commit()
        yield conn
        conn.close()

    def test_top_stores_net_revenue_order(self, mem_db):
        """Store A (400) should rank above Store B (30) in the 30-day window."""
        from analytics import top_5_stores_by_net_revenue
        results = top_5_stores_by_net_revenue(mem_db)
        assert results[0]["store_id"] == "S001"
        assert results[0]["net_revenue"] == pytest.approx(400.0)

    def test_top_stores_returns_reduce_revenue(self, mem_db):
        """Returns must reduce Store B's net revenue (not be excluded)."""
        from analytics import top_5_stores_by_net_revenue
        results = top_5_stores_by_net_revenue(mem_db)
        store_b = next(r for r in results if r["store_id"] == "S002")
        assert store_b["net_revenue"] == pytest.approx(30.0)

    def test_return_rate_flagging(self, mem_db):
        """Store B has 1 return out of 2 transactions = 50% — must be FLAGGED."""
        from analytics import return_rate_by_store
        results = return_rate_by_store(mem_db)
        store_b = next(r for r in results if r["store_id"] == "S002")
        assert store_b["flag"] == "FLAGGED"
        assert store_b["return_rate_pct"] == pytest.approx(50.0)

    def test_customers_excludes_guests(self, mem_db):
        """Top customers query must exclude guest transactions."""
        from analytics import top_10_customers_by_lifetime_spend
        results = top_10_customers_by_lifetime_spend(mem_db)
        customer_ids = [r["customer_id"] for r in results]
        assert "CUST_GUEST" not in customer_ids
