import glob
import os
import pandas as pd

CATEGORY_ORDER = {"type": 0, "variable": 1, "function": 2}

src_dir = os.path.join(os.path.dirname(__file__), "src")
csv_files = glob.glob(os.path.join(src_dir, "*.csv"))

frames = [pd.read_csv(f) for f in csv_files]
combined = pd.concat(frames, ignore_index=True)
combined = combined.dropna(how="all")

combined["_cat_order"] = combined["category"].map(CATEGORY_ORDER)
combined = combined.sort_values(
    by=["_cat_order", "external_item", "file_name", "line_number"],
    ascending=[True, True, True, True],
).drop(columns=["_cat_order"]).reset_index(drop=True)

out_path = os.path.join(os.path.dirname(__file__), "combined.csv")
combined.to_csv(out_path, index=False)
print(f"Written {len(combined)} rows to {out_path}")
