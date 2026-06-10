# Phase 3 Research Report: R External Item Extraction from `rpart/src/`

**Date:** 2026-06-10
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session executed a systematic batch extraction of R API external references (macros, types, and functions) from all C and header source files in the `rpart/src/` directory. The `extract-c-file-r-extern-items` subagent was invoked per-file to identify identifiers declared in the R include headers (`~/.conda/envs/r-to-python/lib/R/include/`). Results were serialized as per-file CSV reports and consolidated into a single sorted master table (`r_extern_analysis/combined.csv`) containing 235 reference entries across 51 unique R external identifiers.

---

### 2. Methodology & Actions Taken

#### 2.1 File Discovery
All 35 C source and header files in `rpart/src/` were enumerated via recursive `find`, comprising 32 `.c` files and 3 `.h` files (`func_table.h`, `node.h`, `rpart.h`, `rpartproto.h`).

#### 2.2 Per-File Extraction
The `extract-c-file-r-extern-items` subagent was invoked sequentially for each file. Agents were batched in parallel groups of up to 5 to reduce total wall time. Each agent:
1. Read the source file and all transitively included local headers (`rpart.h`, `node.h`, `rpartproto.h`).
2. Searched the R include directory to determine whether each non-standard identifier was declared there.
3. Returned a flat CSV with schema: `external_item, header_file, category, file_name, line_number, context_statement`.

The critical disambiguation applied throughout: local wrapper macros in `rpart.h` (`ALLOC`, `CALLOC`, `RPARTNA`, `LEFT`, `RIGHT`) were consistently excluded, as they are declared in the local project header — not in the R include directory — even though they wrap R API calls (`R_alloc`, `R_chk_calloc`, `ISNAN`).

#### 2.3 CSV Output
Per-file CSVs were saved to `r_extern_analysis/src/` using the naming convention `<original_filename>.csv` (e.g., `rpart.c` → `rpart.c.csv`, `rpart.h` → `rpart.h.csv`). An initial naming convention (stripping the original extension) was corrected mid-session after a command-file update; all 35 files were renamed via a shell `mv` loop.

#### 2.4 Combination Script
`r_extern_analysis/combine_csvs.py` was written using `pandas`. It reads all `*.csv` files from `r_extern_analysis/src/`, concatenates them, drops all-`NaN` rows (empty header-only files), and sorts by: (1) `category` in custom order `type → variable → function`, (2) `external_item` alphabetically, (3) `file_name` alphabetically, (4) `line_number` ascending. The sort key was revised once during the session to add `external_item` as the second sort level.

---

### 3. Key Findings & Results

#### 3.1 Coverage Statistics
| Metric | Value |
|--------|-------|
| Total source files analyzed | 35 |
| Files with ≥1 R external reference | 16 |
| Files with zero R external references | 19 |
| Total reference rows in `combined.csv` | 235 |
| Unique R external identifiers | 51 |

#### 3.2 Category Breakdown
| Category | Count |
|----------|-------|
| `function` | 184 (78.3%) |
| `type` | 39 (16.6%) |
| `variable` | 12 (5.1%) |

#### 3.3 R Header Attribution
| R Header | Reference Count |
|----------|----------------|
| `Rinternals.h` | 165 |
| `R_ext/Print.h` | 28 |
| `R_ext/Error.h` | 9 |
| `R_ext/Boolean.h` | 7 |
| `R_ext/Rdynload.h` | 6 |
| `R_ext/RS.h` | 6 |
| `R_ext/Arith.h` | 5 |
| `Rversion.h` | 4 |
| `R.h` | 3 |
| `R_ext/Utils.h` | 2 |

#### 3.4 Files With R External References
`branch.c`, `free_tree.c`, `init.c`, `insert_split.c`, `nodesplit.c`, `pred_rpart.c`, `print_tree.c`, `rpart.c`, `rpart.h`, `rpart_callback.c`, `rpartexp2.c`, `rpartproto.h`, `rundown.c`, `rundown2.c`, `xpred.c`, `xval.c`.

#### 3.5 Files With No R External References
`anova.c`, `anovapred.c`, `bsplit.c`, `choose_surg.c`, `fix_cp.c`, `func_table.h`, `gini.c`, `graycode.c`, `make_cp_list.c`, `make_cp_table.c`, `mysort.c`, `node.h`, `partition.c`, `poisson.c`, `rpartexp.c`, `rpcountup.c`, `rpmatrix.c`, `surrogate.c`, `usersplit.c`. These files rely exclusively on local project abstractions and standard C primitives.

#### 3.6 Notable Technical Observations
- `rpart.c` and `xpred.c` are the most R-API-dense files, making heavy use of `SEXP`, `PROTECT`/`UNPROTECT`, `allocVector`/`allocMatrix`, `INTEGER`, `REAL`, and `SET_VECTOR_ELT`/`SET_STRING_ELT` for constructing and returning R list objects.
- `rpart_callback.c` uniquely uses `eval`, `findVar`/`findVarInFrame`, and `install` — R interpreter-level functions required for callback-based user-defined split evaluation.
- `print_tree.c` contributes 26 rows, all from a single R external item (`Rprintf`), the highest single-function repetition in the dataset.
- `rpart.h` itself references 3 R external items (`R_alloc`, `R_chk_calloc`, `ISNAN`) within its local macro definitions — confirming it as the primary R API abstraction layer for the package.

---

### 4. Conclusion & Next Steps

All 35 files in `rpart/src/` were successfully analyzed. The complete R external item inventory is available in `r_extern_analysis/combined.csv` (235 rows, 51 unique items) and as per-file CSVs in `r_extern_analysis/src/`. The `combine_csvs.py` script is reproducible and can be re-run after any per-file CSV update. The natural next step is to use `combined.csv` as a reference map for implementing Python equivalents of the identified R API calls during the C-to-Python translation phase of the project.
