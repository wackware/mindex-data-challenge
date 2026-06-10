"""Quick script to run profiler against all raw files and print key findings."""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

import pandas as pd
from profiler import profile

raw = {n: pd.read_csv(f"data/raw/{n}.csv") for n in ("stores", "products", "transactions")}
report = {n: profile(df, n) for n, df in raw.items()}

pathlib.Path("output").mkdir(exist_ok=True)
with open("output/profiling_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)

for name, r in report.items():
    print(f"\n=== {name} ({r['row_count']} rows, {r['duplicate_row_count']} dupes) ===")
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
            extras.append(f"dates={info['min_date']}..{info['max_date']}")
        if extras:
            print(f"  {col}: {', '.join(extras)}")

print("\nReport written to output/profiling_report.json")
