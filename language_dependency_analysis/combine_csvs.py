import glob, os
import pandas as pd

input_dir = os.path.join(os.path.dirname(__file__), "R")
output_path = os.path.join(os.path.dirname(__file__), "combined_table.csv")
csv_files = glob.glob(os.path.join(input_dir, "**", "*.csv"), recursive=True)
frames = []
for f in csv_files:
    df = pd.read_csv(f)
    rel_path = os.path.splitext(os.path.relpath(f, input_dir))[0] + ".R"
    df.insert(df.columns.get_loc("function_name"), "file_path", rel_path)
    frames.append(df)
df = pd.concat(frames, ignore_index=True)
df.sort_values(
    by=["language_dependency", "file_path", "function_name", "line_number"],
    inplace=True,
    ignore_index=True,
)
df.to_csv(output_path, index=False)
