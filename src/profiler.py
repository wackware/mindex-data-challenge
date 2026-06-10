"""
profiler.py — Data quality profiling for any DataFrame.

Returns a dict summary: row/col counts, per-column nulls, duplicates,
numeric stats, and date range / future-date count for date-like columns.
"""
import warnings
import pandas as pd
from datetime import date


def profile(df: pd.DataFrame, name: str) -> dict:
    """Return a quality summary dict for `df`. Safe to call on any shape."""
    result = {
        "name": name,
        "row_count": len(df),
        "col_count": len(df.columns),
        "duplicate_row_count": int(df.duplicated().sum()),
        "columns": {},
    }

    for col in df.columns:
        series = df[col]
        null_count = int(series.isnull().sum())
        null_pct = round(null_count / len(series) * 100, 2) if len(series) > 0 else 0.0

        col_info: dict = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": null_pct,
        }

        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            col_info.update({
                "min":            float(non_null.min())  if len(non_null) > 0 else None,
                "max":            float(non_null.max())  if len(non_null) > 0 else None,
                "mean":           round(float(non_null.mean()), 4) if len(non_null) > 0 else None,
                "zero_count":     int((series == 0).sum()),
                "negative_count": int((series < 0).sum()),
            })

        elif not pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        parsed = pd.to_datetime(non_null, errors="coerce")
                    # Treat as date-like if ≥80% of non-null values parsed successfully
                    if parsed.notna().mean() >= 0.8:
                        today = pd.Timestamp(date.today())
                        valid = parsed.dropna()
                        col_info.update({
                            "min_date":         str(valid.min().date()) if len(valid) > 0 else None,
                            "max_date":         str(valid.max().date()) if len(valid) > 0 else None,
                            "future_date_count": int((parsed > today).sum()),
                        })
                except Exception:
                    pass

        result["columns"][col] = col_info

    return result
