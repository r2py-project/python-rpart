# Research Report — Phase 1: C Source Dependency Analysis

**Date**: 2026-06-09
**Working Directory**: `/groups/jli9/Yufei/python-rpart`
**Analyst**: Yufei Cai

---

### 1. Abstract

This session completed Phase 1 of the R-to-Python translation project for the `rpart` package: a full structural dependency analysis of all C source files in `rpart/src/`. Thirty-five `.c` and `.h` files were analyzed function-by-function, producing a consistent set of JSON dependency maps that were subsequently used to generate a dependency graph and a topologically ordered function level schedule.

---

### 2. Methodology & Actions Taken

**Step 1 — JSON Dependency Extraction (`/analyze-c-folder-dependencies`)**

All 35 files in `rpart/src/` were identified via `find` and analyzed sequentially using the `analyze-c-file-dependencies` subagent. Each file was processed individually; results were saved to `c_refactor_analysis/src/` following the naming convention `<filename>.json`. Files analyzed:

- 28 `.c` files: `anova.c`, `anovapred.c`, `branch.c`, `bsplit.c`, `choose_surg.c`, `fix_cp.c`, `free_tree.c`, `gini.c`, `graycode.c`, `init.c`, `insert_split.c`, `make_cp_list.c`, `make_cp_table.c`, `mysort.c`, `nodesplit.c`, `partition.c`, `poisson.c`, `pred_rpart.c`, `print_tree.c`, `rpart.c`, `rpart_callback.c`, `rpartexp.c`, `rpartexp2.c`, `rpcountup.c`, `rpmatrix.c`, `rundown.c`, `rundown2.c`, `surrogate.c`, `usersplit.c`, `xpred.c`, `xval.c`
- 4 `.h` files: `func_table.h`, `node.h`, `rpart.h`, `rpartproto.h`

Each JSON entry records, per function, its `internal_dependencies` (calls resolved within the project) and `external_dependencies` (R API calls such as `R_alloc`, `PROTECT`, `error`, etc.).

**Step 2 — Inconsistency Audit**

All 35 JSON files were cross-examined programmatically. Three inconsistencies were identified and corrected:

1. **`xpred.c.json`** (`xpred`): `rp_init` and `rp_eval` were missing from `internal_dependencies` despite being called as `(*rp_init)(...)` and `(*rp_eval)(...)` at lines 193, 275–276 of `xpred.c`. Both are correctly listed in the analogous entries in `rpart.c.json` and `xval.c.json`. Added both to `xpred`'s internal dependencies.

2. **`rpart_callback.c.json`** (`_` macro definition): The `_` macro in `rpart_callback.c` is defined identically to the one in `rpart.h` (conditionally expands to `dgettext("rpart", ...)` when `ENABLE_NLS` is set), yet its JSON entry listed no external dependencies. Corrected to match `rpart.h.json`: added `dgettext` to `external_dependencies`.

3. **`rpart_callback.c.json`** (`init_rpcallback`): `_` was incorrectly listed as a direct internal dependency. Inspection of the source confirmed that `_()` is called only inside `compat_getVar` (line 24), not inside `init_rpcallback`. Removed `_` from `init_rpcallback`'s `internal_dependencies`.

**Step 3 — Orphaned Node Resolution**

Running `dependency_graph.py` revealed 5 internal dependencies referenced in the JSONs but absent as defined entries in any file:

| Identifier | Type | Declared in |
|---|---|---|
| `rp_init` | `EXTERN` function pointer variable | `rpart.h` |
| `rp_choose` | `EXTERN` function pointer variable | `rpart.h` |
| `rp_eval` | `EXTERN` function pointer variable | `rpart.h` |
| `rp_error` | `EXTERN` function pointer variable | `rpart.h` |
| `impurity` | `static` function pointer variable | `gini.c` |

These are runtime-dispatch function pointer variables, not function definitions. All five were added as entries with empty dependency lists to `rpart.h.json` and `gini.c.json` respectively, resolving all dangling graph nodes.

**Step 4 — Script Execution**

- `networkx 3.6.1` was installed into the `r-to-python` conda environment (missing dependency).
- `dependency_graph.py` and `dependency_levels.py` were each run twice: once before orphan resolution (producing incomplete output) and once after (producing the final outputs).

---

### 3. Key Findings & Results

**Graph metrics (final run):**
- **Files loaded**: 35
- **Nodes**: 136 (35 file nodes, 66 function/macro nodes, 35 external dependency nodes)
- **Edges**: 255
- **Outputs**: `dependency_graph.png`, `dependency_graph.pdf`, `dependency_graph.html`, `dependency_levels.csv`

**Topological level distribution (`dependency_levels.csv`):**

| Level | Count | Description |
|---|---|---|
| 0 | 38 | Entry points / leaves (no unresolved internal callers) |
| 1 | 24 | Functions whose internal deps are all level-0 |
| 2 | 4 | Top-level callers: `ALLOC`, `rp_error`, `compat_getVar`, `branch` |

- **Leaf functions** (no internal calls at all): 47 out of 66

**Notable structural observations:**
- `rpart.c` (`rpart`) is the primary integration point, calling 12 internal functions and 15 R API functions.
- `xpred.c` (`xpred`) and `xval.c` (`xval`) are the two cross-validation entry points; both dispatch through `rp_init` and `rp_eval` function pointers.
- `rpart_callback.c` is fully self-contained (does not include `rpart.h`) and implements its own `_` and `R_getVar` macros for R version compatibility (R < 4.5.0 vs. R ≥ 4.5.0).
- `rpartproto.h` contains only forward declarations; all its entries have empty dependency lists and serve purely as a declaration layer.

---

### 4. Conclusion & Next Steps

Phase 1 is complete. All 35 C source files have been analyzed, their per-function dependency maps are consistent and fully resolved (0 orphaned internal nodes), and the dependency graph and level schedule have been generated. The `dependency_levels.csv` provides a bottom-up conversion order for Phase 2: functions at Level 0 with no internal calls (47 pure leaves) can be translated to Python first, followed by Level 1, and finally Level 2, ensuring that each function's dependencies exist in Python before the function itself is converted.
