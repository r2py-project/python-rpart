---
name: combine-python-functions-into-folder
description: Combines all converted Python functions from the output of /convert-r-folder-to-python into one Python file per R source file, then audits __init__.py for correctness and verifies the package builds cleanly.
---

# Combine Converted Python Functions into a Folder

## Description

Given a folder that was produced by `/convert-r-folder-to-python` (containing one subdirectory per R source file, each holding per-function JSON files), assemble the per-function JSON files for every R file into a unified Python module, name each output file after its R counterpart (`.R` -> `.py`), and then audit the package's `__init__.py` to ensure all public interfaces are correctly exposed. If the package cannot be imported or run cleanly, fix any issues before finishing.

## Parameters

| Parameter | Required | Description |
|---|---|---|
| `conversion_output_folder` | Yes | Path to the folder produced by `/convert-r-folder-to-python`. Contains one subdirectory per R file (e.g., `conversion_results/R/all.R/`, `conversion_results/R/build.R/`). |
| `python_output_folder` | Yes | Path to the target Python package folder where the combined `.py` files will be written (e.g., `r2py_rpart/r2py_rpart/`). |
| `python_package_folder` | No | Root of the Python package tree used for import resolution and `__init__.py` auditing. Defaults to `python_output_folder`. |

## Execution Steps

### Step 1: Discover All Conversion Subdirectories

- Scan `conversion_output_folder` for **immediate subdirectories** (do not recurse deeper).
- Each subdirectory name is an R source filename (e.g., `all.R`, `build.R`, `methods.R`).
- A subdirectory qualifies if it contains **at least one `.json` file** directly inside it.
- Compile a complete, deterministic list of qualifying subdirectories, sorted alphabetically by name.
- Log the discovered list to the console:

```
Discovered <N> conversion subdirectory(ies) in <conversion_output_folder>:
  [1] <subdir_name_1>  (<K> JSON file(s))
  [2] <subdir_name_2>  (<K> JSON file(s))
  ...
```

If no qualifying subdirectories are found, exit immediately with:

```
ERROR: No conversion subdirectories with JSON files found in <conversion_output_folder>. Nothing to combine.
```

### Step 2: Derive Target Python File Names

For each qualifying subdirectory discovered in Step 1:

1. Take the subdirectory name (e.g., `all.R`).
2. Strip the `.R` or `.r` extension and append `.py` (e.g., `all.py`).
3. The target Python file path is `{python_output_folder}/{derived_name}` (e.g., `src/mypkg/all.py`).
4. Log the mapping:

```
Mapping:
  <subdir_name_1>  ->  <target_python_path_1>
  <subdir_name_2>  ->  <target_python_path_2>
  ...
```

### Step 3: Execute Sequential Combinations

Iterate through the sorted list from Step 1 **one subdirectory at a time**. For each subdirectory:

1. **Invoke `/combine-python-functions-into-file`**, passing the following explicit context:
   - The absolute path to the current conversion subdirectory as the **source folder**.
   - The absolute path to the derived target Python file (from Step 2) as the **target file**.
2. **Non-blocking error handling:** If `/combine-python-functions-into-file` fails or exits abnormally, output a clear error message and proceed to the next subdirectory. Do not halt the batch:

   ```
   ERROR: /combine-python-functions-into-file failed for <subdir_name>. Reason: <error_message>. Proceeding to next subdirectory.
   ```

### Step 4: Audit `__init__.py`

After all combinations have been attempted, audit the `__init__.py` file located in `python_package_folder` (defaulting to `python_output_folder` if not specified).

Perform the following checks and apply fixes in-place:

1. **Remove stale or unnecessary imports:** Any symbol imported or re-exported in `__init__.py` that no longer exists in any module inside `python_package_folder` must be removed.
2. **Ensure all public interfaces are exposed:** For every `.py` file written in Step 3 (excluding `__init__.py` itself), verify that each top-level public function (names not prefixed with `_`) is importable via the package. If any are missing from `__init__.py`, add the appropriate import or `__all__` entry.
3. **No duplicate entries:** Deduplicate any import lines or `__all__` entries that appear more than once.
4. **Preserve existing hand-written content:** Do not remove comments, conditional logic, or imports that are still valid and used.

Log every change made to `__init__.py`:

```
__init__.py audit:
  Removed : <symbol_or_import>  (reason: no longer exists in package)
  Added   : <symbol_or_import>  (reason: public interface missing from exports)
  ...
  No changes required.  <- (if everything was already correct)
```

### Step 5: Verify the Package Builds and Runs Cleanly

After the audit:

1. **Import check:** Attempt to import the package from its directory to verify there are no syntax errors or broken imports. Report the result:

   ```
   Import check: PASSED  <- or FAILED: <error>
   ```

2. **If the import fails:** Diagnose the root cause by reading the error traceback carefully. Apply targeted fixes to the affected files (imports, missing symbols, typos, indentation errors). Re-run the import check after each fix. Repeat until the import succeeds or you have exhausted reasonable automated remediation.

3. **Report remaining issues:** If automated remediation cannot fully resolve an import failure, describe exactly which file and line need manual attention.

### Step 6: Report Summary

Print a final summary:

```
========================================
 Combine Python Functions into Folder -- Summary
========================================
 Conversion output folder : <conversion_output_folder>
 Python output folder     : <python_output_folder>
 Package folder           : <python_package_folder>
----------------------------------------
 Subdirectories found     : <N_total>
 Combinations attempted   : <N_attempted>
 Succeeded                : <N_ok>
 Failed                   : <N_err>
 __init__.py changes      : <N_changes>
 Import check             : PASSED / FAILED
========================================
```

If any combination step failed, list the affected subdirectories:

```
Failed subdirectories:
  - <subdir_1>  Reason: <error_1>
  - <subdir_2>  Reason: <error_2>
```
