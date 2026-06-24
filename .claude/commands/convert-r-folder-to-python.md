---
name: convert-r-folder-to-python
description: Converts all functions in all R files within a folder to Python by scanning recursively and sequentially invoking /convert-r-file-to-python for each file.
---

# Convert All R Files in a Folder to Python

## Description

Translate every R file within a target directory into Python. You will be given the path to the R source folder, a folder containing pre-computed JSON dependency maps (one per R file, produced by `/analyze-r-folder-dependencies`), a CSV dependency graph, and a language dependency conversion guide folder. For each R file discovered, you must derive its corresponding JSON map and invoke `/convert-r-file-to-python` to handle the per-file translation.

## Parameters

| Parameter | Required | Description |
|---|---|---|
| `r_folder` | Yes | Path to the folder containing the R source files to convert. |
| `json_folder` | Yes | Path to the folder containing the per-file JSON dependency maps (e.g., `structural_analysis/R/`). Each JSON file must share the same base name as its corresponding R file (e.g., `all.R` → `all.json`). |
| `csv_dependency_graph` | Yes | Path to the CSV dependency graph file (e.g., `structural_analysis/dependency_levels.csv`) that maps functions to their inter-file dependency levels. |
| `language_guides_folder` | Yes | Path to the folder containing language dependency conversion guides (one `.md` file per R language construct). |
| `target_output_folder` | No | Root folder for all converted output. Defaults to `conversion_results/R/`. Each R file's functions will be written to `{target_output_folder}/{R_file_name}/` as per `/convert-r-file-to-python` conventions. |

## Execution Steps

### Step 1: Discover All R Files

- Recursively scan `r_folder` and all of its subdirectories.
- Identify every file whose name ends with `.R` or `.r`.
- Compile a complete, deterministic list of their absolute paths, sorted alphabetically.
- Log the discovered file list to the console:

```
Discovered <N> R file(s) in <r_folder>:
  [1] <absolute_path_1>
  [2] <absolute_path_2>
  ...
```

### Step 2: Resolve JSON Dependency Maps

For each R file discovered in Step 1:

1. Derive the expected JSON dependency map path by replacing the file's `.R` or `.r` extension with `.json` and looking it up within `json_folder`. Use only the base filename — do not replicate subdirectory structure inside `json_folder` unless the JSON files are organized the same way.
   - *Example:* `{r_folder}/all.R` → `{json_folder}/all.json`
2. Verify that the derived JSON file exists on disk.
3. If the JSON file does **not** exist, log a warning and mark that R file as **skipped**:
   ```
   WARNING: No JSON dependency map found for <r_file> (expected <json_path>). Skipping.
   ```
4. Retain only files for which a corresponding JSON map was successfully located. These form the **execution queue**.

### Step 3: Sort the Execution Queue by Dependency Level

Before executing, sort the execution queue to respect inter-file dependency order.

1. Parse the CSV dependency graph at `csv_dependency_graph`.
2. For each R file in the execution queue, match rows by the file's **base name** against the `r_file` column.
3. For each matching row, extract the numeric level by stripping the optional ` (leaf)` suffix (e.g., `"4 (leaf)"` → `4`).
4. Compute the **maximum level** across all matched rows for each file. If a file has no rows in the CSV, treat its maximum level as `0`.
5. Sort the execution queue in **descending order of maximum level** (files with the highest-level functions — deepest callees — are processed first, because other files depend on their outputs). Break ties alphabetically.
6. Log the sorted execution order to the console:

```
Execution order (sorted by max dependency level, highest first):
  [1] <r_file_1>  (max level: <L>)
  [2] <r_file_2>  (max level: <L>)
  ...
```

### Step 4: Execute Sequential Conversions

Iterate through the **sorted** execution queue from Step 3 one file at a time. For each R file:

1. **Invoke `/convert-r-file-to-python`**, passing the following explicit context:
   - The absolute path to the current R source file.
   - The absolute path to the corresponding JSON dependency map (resolved in Step 2).
   - The absolute path to the CSV dependency graph (`csv_dependency_graph`).
   - The absolute path to the language dependency conversion guides folder (`language_guides_folder`).
   - The target output folder (`target_output_folder`). If not provided by the user, use the default `conversion_results/R/`.

2. **Non-blocking error handling:** If `/convert-r-file-to-python` fails, throws an error, or exits abnormally for a specific file, output a clear error message to the console and immediately proceed to the next file. Do not halt the batch:
   ```
   ERROR: /convert-r-file-to-python failed for <r_file>. Reason: <error_message>. Proceeding to next file.
   ```

### Step 5: Report Summary

After all files in the execution queue have been attempted, print a final summary:

```
========================================
 Convert R Folder to Python — Summary
========================================
 R source folder      : <r_folder>
 JSON dependency maps : <json_folder>
 CSV dependency graph : <csv_dependency_graph>
 Language guides      : <language_guides_folder>
 Target output folder : <target_output_folder>
----------------------------------------
 Total R files found  : <N_total>
 Skipped (no JSON)    : <N_skipped>
 Attempted            : <N_attempted>
 Succeeded            : <N_ok>
 Failed               : <N_err>
========================================
```

If any file failed, list them explicitly so the user knows which files to retry:

```
Failed files:
  - <r_file_1>  Reason: <error_1>
  - <r_file_2>  Reason: <error_2>
```