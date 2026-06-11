# Mindex Data Engineer Challenge — Submission

**Author:** Christopher R. Wack  
**Submitted:** 2026-06-10  
**Repo:** https://github.com/wackware/mindex-data-challenge

---

## Setup & Run

```bash
# 1. Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# or: .venv/bin/pip install -r requirements.txt  # Mac/Linux

# 2. (Optional) Regenerate raw data
python scripts/seed_data.py

# 3. Run full pipeline (profile → clean → load → analytics — generates all 4 outputs)
run.bat          # Windows
# or: .venv/bin/python src/pipeline.py

# 4. Run data quality profiler (standalone)
profile.bat      # Windows — writes output/profiling_report.json
# or: .venv/bin/python scripts/run_profile.py

# 5. Run tests
test.bat         # Windows
# or: .venv/bin/pytest tests/ -v

# 6. View results (human-friendly ASCII tables for all 4 output files)
view.bat         # Windows
# or: .venv/bin/python scripts/view_output.py
```

**Outputs generated:**

| File | Description |
|---|---|
| `output/profiling_report.json` | Data quality profile of all 3 raw files |
| `output/warehouse.db` | SQLite star schema warehouse |
| `output/exclusions.json` | Rows excluded from fact_sales with reason |
| `output/analytics.json` | Results for all 5 business questions |

---

## Architecture

```
data/raw/
  transactions.csv
  stores.csv          ──► src/profiler.py ──► output/profiling_report.json
  products.csv               │
                             ▼
                      src/cleaner.py
                   (clean DataFrames)
                             │
                             ▼
                      src/loader.py ──► output/warehouse.db
                             │          dim_date
                             │          dim_store
                             │          dim_product
                             │          dim_customer
                             │          fact_sales
                             │
                             ▼
                     src/analytics.py ──► output/analytics.json
                                                   │
                                                   ▼
                                        scripts/view_output.py  (view.bat)
                                        human-friendly ASCII table display

src/pipeline.py   ← orchestrates all stages in order
tests/test_pipeline.py  ← pytest suite (TDD, 25 tests)
```

**Design principle**: Each module has one responsibility. `pipeline.py` is the entry point and calls them in order. Any stage can be tested or re-run in isolation.

---

## Data Quality Findings

> Counts confirmed from output/profiling_report.json (run 2026-06-10). Mixed-format and orphan counts from seed_data.py analysis; all others profiler-verified.

| Issue | File | Count | Decision | Rationale |
|---|---|---|---|---|
| Mixed date formats (MM/DD/YYYY and DD-MM-YYYY) | transactions.csv | 20 | Normalize all to YYYY-MM-DD | Downstream date math requires consistent format; `pd.to_datetime` handles all three variants |
| String-formatted amounts ("$12.50") | transactions.csv | 25 | Strip `$`, cast to float | Numeric operations require float; `$` is a display artifact from the source system |
| Silent discounts (total_amount ≠ qty × unit_price) | transactions.csv | 20 | Keep actual total_amount; add `has_price_discrepancy` flag | The transaction amount is ground truth for revenue. The discrepancy may be a coupon or override — flagged for review, not discarded |
| Orphaned store_ids (S016–S019) | transactions.csv | 5 | Exclude from fact_sales; log to exclusions.json | Cannot dimension without a valid store; including would corrupt store-level analytics |
| Orphaned product_ids (P031, P032) | transactions.csv | 3 | Exclude from fact_sales; log | Same rationale — referential integrity required for analytics |
| NULL customer_id (guest transactions) | transactions.csv | 40 | Map to synthetic CUST_GUEST in dim_customer; include in fact_sales | Guest transactions are real revenue. Excluding would skew store/product totals. `is_guest = 1` flag enables filtering in analytics |
| Zero-quantity rows | transactions.csv | 5 | Exclude from fact_sales | No business event occurred. Including would distort average transaction value |
| Future-dated rows | transactions.csv | 3 injected (count decreases as dates become current) | Exclude from fact_sales; log | Future dates in a historical export are data entry errors. Including would corrupt date-window analytics |
| Exact duplicate transaction rows (same TXN ID) | transactions.csv | 15 | Deduplicate, keep first | True duplicates from a bad extract. Keeping both would double-count revenue |
| Return transactions (negative qty + amount) | transactions.csv | 30 | Include with `is_return = 1` flag | Returns are real business events. Net revenue queries use `SUM(total_amount)` which naturally subtracts returns. Excluding would overstate revenue |
| Near-duplicate store S007 (same ID, two names) | stores.csv | 1 extra row | Keep first; document both names | Cannot have two rows with the same PK in dim_store. Both names refer to the same physical location |
| Malformed zip S003 ("0938" — 4 digits) | stores.csv | 1 | Keep with `zip_valid = 0` flag | Dropping would orphan all S003 transactions. Zip is reference data, not used in analytics. Flagged for upstream correction |
| NULL region (S013, S014 — Portland stores) | stores.csv | 2 | Set region = 'Unknown' | NULL would break GROUP BY region analytics. 'Unknown' is honest and queryable |
| Exact duplicate product row P012 | products.csv | 1 | Deduplicate, keep first | Bad extract artifact; rows are identical |
| Two prices for P005 | products.csv | 1 conflict | Use latest price in dim_product; use transaction's actual unit_price in fact_sales | dim_product holds current catalog state. fact_sales preserves historical transaction prices. This is standard Kimball practice |
| NULL category (P003, P009, P016, P023, P029) | products.csv | 5 | Set category = 'Uncategorized' | NULL would break GROUP BY category. 'Uncategorized' is honest and queryable |
| Zero unit_price P027 | products.csv | 1 | Keep; add `price_is_zero = 1` flag | Could be a promotional/free item. Dropping would lose real transactions. Flagged for business review |

---

## Schema Design

```sql
-- dim_date: one row per calendar date in the transaction window
CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- YYYYMMDD integer
    full_date    TEXT NOT NULL,
    year         INTEGER,
    month        INTEGER,
    day          INTEGER,
    quarter      INTEGER,
    day_of_week  TEXT,
    month_name   TEXT
);

-- dim_store: one row per unique store
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

-- dim_product: one row per product (latest price)
CREATE TABLE dim_product (
    product_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    TEXT NOT NULL UNIQUE,
    product_name  TEXT,
    category      TEXT,
    unit_price    REAL,
    supplier_id   TEXT,
    price_is_zero INTEGER DEFAULT 0
);

-- dim_customer: one row per customer + one synthetic CUST_GUEST row
CREATE TABLE dim_customer (
    customer_key  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   TEXT UNIQUE,
    is_guest      INTEGER DEFAULT 0
);

-- fact_sales: one row per transaction (includes returns)
CREATE TABLE fact_sales (
    transaction_id           TEXT PRIMARY KEY,
    date_key                 INTEGER REFERENCES dim_date(date_key),
    store_key                INTEGER REFERENCES dim_store(store_key),
    product_key              INTEGER REFERENCES dim_product(product_key),
    customer_key             INTEGER REFERENCES dim_customer(customer_key),
    quantity                 INTEGER,
    unit_price               REAL,
    total_amount             REAL,
    is_return                INTEGER DEFAULT 0,
    has_price_discrepancy    INTEGER DEFAULT 0
);
```

**Key modeling decisions:**
- `dim_customer` is added beyond the minimum spec because guest transactions need a home row — otherwise fact_sales would have a nullable FK which breaks star schema integrity.
- Surrogate integer keys (`store_key`, `product_key`, etc.) are used as FKs in fact_sales. Natural keys (`store_id`, `product_id`) remain in the dim tables for display and lookup.
- `date_key` is an integer in YYYYMMDD form — fast range filtering without string comparison.
- `is_return` flag keeps returns in the fact table, allowing both gross and net revenue calculations without separate tables.

---

## Analytics Results

> Confirmed from `output/analytics.json` run 2026-06-10. Note: June data is partial (through June 10 only), which explains the sharp MoM decline for June figures.

### Q1 — Top 5 Stores by Net Revenue (most recent 30 days)

30-day window: 2026-05-11 → 2026-06-10 (from max transaction date).

| Rank | Store | Store ID | Net Revenue |
|---|---|---|---|
| 1 | Eastview Mall | S001 | $5,059.97 |
| 2 | Lloyd Center | S014 | $4,228.32 |
| 3 | Galleria at Crystal Run | S008 | $4,023.80 |
| 4 | Crossroads Center | S004 | $3,800.70 |
| 5 | Park Place Mall | S010 | $3,704.73 |

Net revenue = `SUM(total_amount)` including returns (returns subtract naturally via negative total_amount).

### Q2 — Month-over-Month Revenue Change by Category

| Category | Mar 2026 | Apr 2026 | MoM % | May 2026 | MoM % | Jun 2026 (partial) |
|---|---|---|---|---|---|---|
| Apparel | $9,844.60 | $11,032.38 | +12.1% | $14,304.78 | +29.7% | $899.03 |
| Electronics | $4,015.66 | $7,313.81 | +82.1% | $12,402.46 | +69.6% | $157.39 |
| Food & Beverage | $1,198.94 | $6,033.43 | +403.2% | $7,902.99 | +31.0% | — |
| Home & Garden | $2,199.83 | $2,717.62 | +23.5% | $4,658.36 | +71.4% | $64.05 |
| Office Supplies | $18,496.95 | $19,855.01 | +7.3% | $12,025.25 | −39.4% | — |
| Uncategorized | $5,939.29 | $7,290.97 | +22.8% | $9,932.69 | +36.2% | $73.56 |

### Q3 — Return Rate by Store

3 stores flagged above 10% threshold:

| Store | Store ID | Return Rate | Flag |
|---|---|---|---|
| Alderwood Mall | S015 | 15.4% | FLAGGED |
| Lakeside Shopping Ctr | S006 | 12.5% | FLAGGED |
| Galleria at Crystal Run | S008 | 11.6% | FLAGGED |

Note: S008 also appears in the top 5 by net revenue — high volume partially explains the elevated return rate.

### Q4 — Average Transaction Value by Region

Returns excluded (WHERE is_return = 0). Portland stores (S013, S014) mapped to 'Unknown' region per DQ table row 13.

| Region | Avg Transaction Value | # Transactions |
|---|---|---|
| Unknown | $396.64 | 64 |
| Northeast | $388.60 | 166 |
| South | $384.49 | 83 |
| Midwest | $375.82 | 46 |
| West | $339.75 | 86 |

### Q5 — Top 10 Customers by Lifetime Spend

Guest transactions excluded (WHERE is_guest = 0). No CUST_GUEST in results.

| Customer ID | Lifetime Spend | Transactions | Avg Order Value |
|---|---|---|---|
| CUST0213 | $3,077.96 | 4 | $769.49 |
| CUST0170 | $2,854.52 | 5 | $570.90 |
| CUST0287 | $2,825.70 | 4 | $706.42 |
| CUST0060 | $2,414.60 | 2 | $1,207.30 |
| CUST0142 | $2,284.70 | 3 | $761.57 |
| CUST0255 | $2,181.57 | 5 | $436.31 |
| CUST0186 | $1,906.56 | 4 | $476.64 |
| CUST0085 | $1,846.65 | 4 | $461.66 |
| CUST0084 | $1,831.43 | 4 | $457.86 |
| CUST0118 | $1,655.79 | 2 | $827.89 |

**Why SQL over pandas**: These are set-based aggregations on a relational schema. SQL is the right tool — cleaner, more readable, and easier for teammates to audit than chained pandas operations.

---

## How I Would Productionize This

**Orchestration**: Replace `pipeline.py` with an Airflow DAG (one task per stage: profile → clean → load → analytics). Task dependencies are explicit. Email-on-failure alert. This maps directly to the Astronomer/Airflow stack I ran at Trajector.

**Incremental loads**: Add a `loaded_at` watermark to `fact_sales`. Each run processes only `WHERE transaction_date > MAX(loaded_at)`. Use `INSERT OR REPLACE` (SQLite) or a proper MERGE (Snowflake/Delta Lake) for upserts.

**Observability**: 
- Great Expectations or dbt tests for post-clean assertions (null rate thresholds, row count checks, FK integrity)
- Alert if exclusions exceed a threshold (e.g., > 2% of input rows)
- Row count reconciliation: source file rows vs. loaded fact rows vs. excluded rows must sum correctly

**Storage upgrade**: The Python code touches SQLite only in `loader.py` and `analytics.py`. Swapping to Snowflake means changing the connection string and replacing `sqlite3` with `snowflake-connector-python`. Schema and SQL are portable.

**CI/CD**: GitHub Actions workflow — `pytest tests/ -v` on every PR, fail merge if tests fail.

---

## What I'd Do Differently With More Time

- **dbt for the transform layer**: Replace the SQL strings in `analytics.py` and the DDL in `loader.py` with dbt models — better lineage, built-in testing, and generated docs.
- **Type-safe dataclass models**: Avoid silent schema drift between cleaning and loading stages.
- **Configurable thresholds**: Null % tolerance, future-date window, return rate flag threshold — currently hardcoded, should be in a config file.
- **Full data lineage**: Track which source rows became which warehouse rows (source file name, row index). Currently only exclusions are tracked.
- **Richer dim_date**: Add fiscal quarter, week-of-year, is_weekend flag for more flexible analytics.
