"""
cleaner.py — Data cleaning pipeline.

Each public function corresponds to one or more rows in the data quality table.
clean_transactions() returns (clean_df, exclusions) where exclusions is a list
of dicts describing rows removed and why.
"""
import warnings
from datetime import date

import pandas as pd


# ── Reusable primitives ───────────────────────────────────────────────────────

def normalize_dates(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Coerce mixed date formats (ISO, MM/DD/YYYY, DD-MM-YYYY) to YYYY-MM-DD."""
    df = df.copy()
    series = df[col]
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        unparsed = result.isna() & series.notna()
        if not unparsed.any():
            break
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(series[unparsed], format=fmt, errors="coerce")
        result.loc[unparsed] = parsed.values

    df[col] = result.dt.strftime("%Y-%m-%d").where(result.notna(), series)
    return df


def strip_dollar(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Strip leading $ from a string-typed numeric column and cast to float."""
    df = df.copy()
    df[col] = df[col].astype(str).str.replace("$", "", regex=False).astype(float)
    return df


# ── Per-source cleaning ───────────────────────────────────────────────────────

def clean_stores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Issues handled:
      - S007 near-duplicate (same store_id, different name): keep first
      - S003 malformed zip (4 digits): keep, add zip_valid=0 flag
      - S013/S014 NULL region: fill 'Unknown'
    """
    df = df.copy()
    df = df.drop_duplicates(subset=["store_id"], keep="first")
    df["zip_valid"] = df["zip_code"].apply(
        lambda z: 1 if str(z).strip().isdigit() and len(str(z).strip()) == 5 else 0
    )
    df["region"] = df["region"].fillna("Unknown")
    return df.reset_index(drop=True)


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    """
    Issues handled:
      - P012 exact duplicate: drop second row
      - P005 two prices (undocumented change): keep latest (last) price per product_id
      - P003/P009/P016/P023/P029 NULL category: fill 'Uncategorized'
      - P027 zero unit_price: keep, add price_is_zero=1 flag
    """
    df = df.copy()
    # Drop fully identical rows first (catches P012)
    df = df.drop_duplicates(keep="first")
    # For same product_id with different values (P005 price conflict), keep last = latest price
    df = df.drop_duplicates(subset=["product_id"], keep="last")
    df["category"] = df["category"].fillna("Uncategorized")
    df["price_is_zero"] = (df["unit_price"] == 0.0).astype(int)
    return df.reset_index(drop=True)


def clean_transactions(
    df: pd.DataFrame,
    valid_store_ids: set,
    valid_product_ids: set,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Issues handled (in order):
      1. Mixed date formats → normalize to YYYY-MM-DD
      2. $-prefixed total_amount → strip and cast to float
      3. Exact duplicate transaction_ids → deduplicate, keep first
      4. Orphaned store_ids → exclude, log
      5. Orphaned product_ids → exclude, log
      6. Zero-quantity rows → exclude, log
      7. Future-dated rows → exclude, log
      8. Silent discounts (total_amount ≠ qty × unit_price) → flag has_price_discrepancy
      9. Returns (negative qty/amount) → flag is_return
     10. NULL customer_id → map to 'CUST_GUEST'

    Returns:
        (clean_df, exclusions) where exclusions is a list[dict] for output/exclusions.json
    """
    df = df.copy()
    exclusions: list[dict] = []

    # 1. Normalize dates
    df = normalize_dates(df, "transaction_date")

    # 2. Strip $ from total_amount (mixed string/numeric column)
    df["total_amount"] = (
        df["total_amount"].astype(str).str.replace("$", "", regex=False).astype(float)
    )

    # 3. Deduplicate by transaction_id
    dupes_mask = df.duplicated(subset=["transaction_id"], keep="first")
    for _, row in df[dupes_mask].iterrows():
        exclusions.append({"transaction_id": row["transaction_id"], "reason": "exact_duplicate"})
    df = df[~dupes_mask]

    # 4. Orphaned store_ids
    orphan_store = ~df["store_id"].isin(valid_store_ids)
    for _, row in df[orphan_store].iterrows():
        exclusions.append({"transaction_id": row["transaction_id"], "reason": f"orphaned_store_id:{row['store_id']}"})
    df = df[~orphan_store]

    # 5. Orphaned product_ids
    orphan_product = ~df["product_id"].isin(valid_product_ids)
    for _, row in df[orphan_product].iterrows():
        exclusions.append({"transaction_id": row["transaction_id"], "reason": f"orphaned_product_id:{row['product_id']}"})
    df = df[~orphan_product]

    # 6. Zero-quantity rows
    zero_qty = df["quantity"].astype(float) == 0
    for _, row in df[zero_qty].iterrows():
        exclusions.append({"transaction_id": row["transaction_id"], "reason": "zero_quantity"})
    df = df[~zero_qty]

    # 7. Future-dated rows
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    today = pd.Timestamp(date.today())
    future = df["transaction_date"] > today
    for _, row in df[future].iterrows():
        exclusions.append({"transaction_id": row["transaction_id"], "reason": f"future_date:{row['transaction_date'].date()}"})
    df = df[~future]
    df["transaction_date"] = df["transaction_date"].dt.strftime("%Y-%m-%d")

    # 8. Silent discount flag
    expected = df["quantity"].astype(float) * df["unit_price"].astype(float)
    df["has_price_discrepancy"] = ((df["total_amount"] - expected).abs() > 0.01).astype(int)

    # 9. Return flag
    df["is_return"] = (df["quantity"].astype(float) < 0).astype(int)

    # 10. Guest customer mapping
    df["customer_id"] = df["customer_id"].fillna("CUST_GUEST")

    return df.reset_index(drop=True), exclusions
