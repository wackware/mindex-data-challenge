"""view_output.py — Human-friendly rendering of all pipeline output files."""
import json
import pathlib
from collections import Counter

OUTPUT = pathlib.Path("output")


def _hr(width=72):
    print("-" * width)


def _table(rows: list[dict], title: str) -> None:
    if not rows:
        print(f"{title}: (empty)")
        return
    print(f"\n{title}")
    _hr()
    cols = list(rows[0].keys())
    widths = {c: max(len(c), max(len(str(r.get(c, "") or "")) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for row in rows:
        print("  ".join(str(row.get(c, "") or "").ljust(widths[c]) for c in cols))


def show_analytics() -> None:
    data = json.loads((OUTPUT / "analytics.json").read_text())
    labels = {
        "top_5_stores_net_revenue":       "Q1 — Top 5 Stores by Net Revenue (30-day window)",
        "mom_revenue_by_category":         "Q2 — Month-over-Month Revenue by Category",
        "return_rate_by_store":            "Q3 — Return Rate by Store",
        "avg_txn_value_by_region":         "Q4 — Avg Transaction Value by Region",
        "top_10_customers_lifetime_spend": "Q5 — Top 10 Customers by Lifetime Spend",
    }
    print("\n=== ANALYTICS RESULTS ===")
    for key, label in labels.items():
        _table(data[key], label)


def show_exclusions() -> None:
    excl = json.loads((OUTPUT / "exclusions.json").read_text())
    print(f"\n=== EXCLUSIONS ({len(excl)} rows excluded) ===")
    _hr()
    for reason, count in Counter(e["reason"].split(":")[0] for e in excl).most_common():
        print(f"  {reason:<35}  {count:>3}")


def show_profiling() -> None:
    profile = json.loads((OUTPUT / "profiling_report.json").read_text())
    print("\n=== DATA PROFILING SUMMARY ===")
    _hr()
    for name, r in profile.items():
        print(f"  {name}: {r['row_count']} rows | {r['col_count']} cols | {r['duplicate_row_count']} dup rows")
        for col, info in r["columns"].items():
            extras = []
            if info["null_count"]:
                extras.append(f"nulls={info['null_count']} ({info['null_pct']}%)")
            if info.get("zero_count"):
                extras.append(f"zeros={info['zero_count']}")
            if info.get("negative_count"):
                extras.append(f"negs={info['negative_count']}")
            if info.get("future_date_count"):
                extras.append(f"future_dates={info['future_date_count']}")
            if info.get("min_date"):
                extras.append(f"range={info['min_date']}..{info['max_date']}")
            if extras:
                print(f"    {col}: {', '.join(extras)}")
        print()


if __name__ == "__main__":
    show_profiling()
    show_exclusions()
    show_analytics()
