# Phase 8.1 Research Report: Language Dependency Extraction — `rpart/R/`

**Date:** 2026-06-22
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session executed a full batch extraction of language dependency usage locations across all 36 R source files in `rpart/R/`, consuming pre-computed structural analysis JSONs from `structural_analysis/R/` and producing per-file CSV reports in `language_dependency_analysis/R/`. The 36 individual CSVs were then merged into a single sorted master table, `language_dependency_analysis/combined_table.csv`, containing 1,298 invocation records across 172 distinct language dependencies. A CSV encoding defect in one generated file was diagnosed and corrected before the merge completed successfully.

---

### 2. Methodology & Actions Taken

#### 2.1 Skill Invocation and Source Scan

The `/extract-r-folder-language-dependencies` skill was invoked with target directory `rpart/R/`. A recursive scan of that directory identified 36 `.R` files:

```
formatg.R, importance.R, labels.rpart.R, meanvar.rpart.R,
model.frame.rpart.R, na.rpart.R, path.rpart.R, plotcp.R,
plot.rpart.R, post.R, post.rpart.R, predict.rpart.R,
pred.rpart.R, printcp.R, print.rpart.R, prune.R,
prune.rpart.R, residuals.rpart.R, roc.rpart.R, rpart.anova.R,
rpart.branch.R, rpartcallback.R, rpart.class.R, rpart.control.R,
rpartco.R, rpart.exp.R, rpart.matrix.R, rpart.poisson.R,
rpart.R, rsq.rpart.R, snip.rpart.mouse.R, snip.rpart.R,
summary.rpart.R, text.rpart.R, xpred.rpart.R, zzz.R
```

All 36 files had matching JSON counterparts in `structural_analysis/R/`.

#### 2.2 Per-File Extraction

The output directory `language_dependency_analysis/R/` was created. Each R file was processed sequentially by the `extract-r-file-language-dependencies` subagent, which was provided the R source path and its paired structural analysis JSON. The agent identified all invocation sites of language dependencies (as pre-catalogued in the JSON), extracted the line number and call body for each, and wrote a 4-column CSV (`language_dependency`, `function_name`, `line_number`, `call_body`) to the output directory.

All 36 files were processed without agent-level failure. Progress was tracked via the `TodoWrite` task list, with each task marked `in_progress` → `completed` immediately upon agent return.

#### 2.3 CSV Merge Execution

The user requested execution of `language_dependency_analysis/combine_csvs.py` inside the `r-to-python` conda environment:

```bash
conda run -n r-to-python python language_dependency_analysis/combine_csvs.py
```

The script uses `glob` to collect all `*.csv` files under `language_dependency_analysis/R/`, reads each with `pandas.read_csv`, inserts a `file_path` column (the relative `.R` path), concatenates all frames, sorts by `["language_dependency", "file_path", "function_name", "line_number"]`, and writes `language_dependency_analysis/combined_table.csv`.

#### 2.4 CSV Defect Diagnosis and Fix

The first execution failed:

```
pandas.errors.ParserError: Error tokenizing data. C error: Expected 4 fields in line 3, saw 7
```

A targeted diagnostic loop identified `rpart.anova.csv` as the offending file. Inspection revealed that the `call_body` fields for both `paste0` rows (lines 6 and 10 of the R source) and the multiline `list` row contained embedded R string literal delimiters (`"  mean="`, `"\nn="`, `", MSE="`) that were written as bare `"` characters rather than the RFC 4180-compliant doubled `""` escape sequence. This caused the CSV parser to split each quoted field at the first interior `"`, producing spurious extra fields.

The fix was applied using Python's `csv.writer` with `quoting=csv.QUOTE_MINIMAL` and `lineterminator='\n'`, which correctly doubles all interior double quotes:

- `"  mean="` → `""  mean=""`
- `"\nn="` → `""\nn=""`
- `", MSE="` → `"", MSE=""`

The corrected file was verified by re-reading it with `pandas.read_csv`, confirming all 4 rows parsed into the expected 4-column DataFrame with accurate `call_body` values.

#### 2.5 Successful Merge

After the fix, `combine_csvs.py` completed without error, writing `language_dependency_analysis/combined_table.csv`.

---

### 3. Key Findings & Results

#### 3.1 Output Metrics

| Metric | Value |
|---|---|
| R source files processed | 36 |
| CSV files generated | 36 |
| Total invocation records (combined table) | 1,298 |
| Distinct language dependencies catalogued | 172 |
| Files containing more than one R function | 7 |

#### 3.2 Files with Highest Invocation Counts

| File | Rows |
|---|---|
| `rpart.R` | 171 |
| `xpred.rpart.R` | 98 |
| `rpart.class.R` | 87 |
| `summary.rpart.R` | 86 |
| `rpart.exp.R` | 74 |

#### 3.3 Most Frequent Language Dependencies

The top 15 most-called base-R language functions across the entire library are:

| Rank | Dependency | Invocations |
|---|---|---|
| 1 | `stop` | 80 |
| 2 | `c` | 67 |
| 3 | `length` | 63 |
| 4 | `is.null` | 60 |
| 5 | `cat` | 41 |
| 6 | `match` | 35 |
| 7 | `list` | 34 |
| 8 | `names` | 34 |
| 9 | `as.integer` | 33 |
| 10 | `format` | 32 |
| 11 | `matrix` | 30 |
| 12 | `missing` | 30 |
| 13 | `any` | 27 |
| 14 | `attr` | 27 |
| 15 | `ncol` | 26 |

#### 3.4 CSV Encoding Defect Root Cause

The defect in `rpart.anova.csv` was introduced by the `extract-r-file-language-dependencies` agent: when generating multi-line `call_body` values that contain R string literals (which use `"` as delimiters), the agent did not double the inner `"` characters per RFC 4180. The defect was isolated to a single file. All other 35 CSVs parsed without error.

#### 3.5 Structural Observations

- Files acting as simple S3 generic dispatchers (`post.R`, `prune.R`) contain a single function with one invocation (`UseMethod`), yielding a 1-row CSV.
- `rpartcallback.R` has 84 invocation records — the densest per-function count among single-function files — reflecting its role as the core C-callback builder with heavy use of `stop` (14 calls), `length` (13 calls), and `assign` (9 calls).
- `rpart.R` contributes 171 rows across two functions (`rpart` and `tfun`), cataloguing 62 and 4 language dependencies respectively.

---

### 4. Conclusion & Next Steps

All 36 language dependency CSV files were successfully generated in `language_dependency_analysis/R/` and merged into `language_dependency_analysis/combined_table.csv` (1,298 rows, 5 columns). The combined table provides a complete, sorted index of every base-R language function call site across the `rpart` library, ready for consumption by downstream conversion guide generation and Python translation workflows.

The natural next step is to invoke `/generate-language-dependency-conversion-guides` against the combined table (or the per-file CSVs) to produce Markdown conversion guides for each of the 172 distinct language dependencies, which will subsequently inform the `/convert-r-file-to-python` agents when translating each R function.
