# Phase 10.1 Research Report: R-to-Python Batch Conversion — `rpart/R/`

**Date:** 2026-06-25
**Working Directory:** `/groups/jli9/Yufei/python-rpart`

---

### 1. Abstract

This session executed the `/convert-r-folder-to-python` skill to translate all 36 R source files in `rpart/R/` into Python equivalents, persisting each converted function as a JSON file under `conversion_results/R/`. The skill processed files in descending dependency-level order (deepest callees first) and functions within each file leaf-to-root, invoking one `convert-r-function-to-python` subagent per function. All 36 files and 47 functions were converted successfully with zero failures.

---

### 2. Methodology & Actions Taken

#### 2.1 Skill Invocation

The `/convert-r-folder-to-python` skill was invoked with the following explicit arguments:

| Parameter | Value |
|---|---|
| `r_folder` | `rpart/R/` |
| `json_folder` | `structural_analysis/R/` |
| `csv_dependency_graph` | `structural_analysis/dependency_levels.csv` |
| `language_guides_folder` | `language_dependency_analysis/conversion_guides/` |
| `target_output_folder` | `conversion_results/R/` |

#### 2.2 Dependency-Level Ordering

The CSV `structural_analysis/dependency_levels.csv` was parsed to assign each R file a maximum dependency level. Files were sorted in descending order of this level, ensuring that low-level utilities (e.g., `rpartco.R` at level 4–5, `snip.rpart.mouse.R` at level 3) were converted before the high-level files that depended on them (e.g., `plot.rpart.R`, `rpart.R` at level 0).

Execution order (abridged, highest-level first):

| Rank | File | Max Level |
|---|---|---|
| 1 | `rpartco.R` | 5 |
| 2 | `zzz.R` | 5 |
| 3 | `rpart.branch.R` | 4 |
| 4 | `snip.rpart.mouse.R` | 3 |
| 5 | `snip.rpart.R` | 2 |
| 6 | `formatg.R`, `importance.R`, `rpart.exp.R` | 2 |
| 7–21 | All level-1 files (`labels.rpart.R`, `na.rpart.R`, `pred.rpart.R`, `printcp.R`, `prune.rpart.R`, `roc.rpart.R`, `rpart.anova.R`, `rpart.class.R`, `rpart.control.R`, `rpart.matrix.R`, `rpart.poisson.R`, `rpartcallback.R`, `text.rpart.R`) | 1 |
| 22–36 | All level-0 files | 0 |

#### 2.3 Within-File Function Ordering

For multi-function files, functions were further sorted leaf-to-root using their individual level values from the CSV:

- **`rpartco.R`**: `compress` (level 5) → `rpartco` (level 4)
- **`zzz.R`**: `tree.depth` (level 5), `descendants`, `node.match`, `string.bounding.box`, `on_unload` (level 1/0)
- **`rpart.exp.R`**: `drate2` (level 2) → `rpart.exp` (level 1)
- **`roc.rpart.R`**: `ss.compare` (level 1) → `roc.rpart` (level 0)
- **`text.rpart.R`**: `oval`, `rectangle` (level 1) → `text.rpart` (level 0)
- **`meanvar.rpart.R`**: `meanvar.rpart`, `meanvar` (both level 0 leaves, parallel)
- **`rpart.R`**: `tfun` (level 0 leaf) → `rpart` (level 0)

#### 2.4 Parallelization

Independent leaf functions across different files were dispatched in parallel using simultaneous `Agent` tool calls to maximize throughput, while within-file sequential constraints were strictly respected. For example, all thirteen level-1 files were converted in parallel batches.

#### 2.5 Individual Conversions and Key Translation Decisions

Each function was converted by the `convert-r-function-to-python` subagent using the corresponding JSON dependency map and the 172 Markdown conversion guides in `language_dependency_analysis/conversion_guides/`. Key cross-cutting decisions applied throughout:

**R → Python idiom mappings:**

| R Construct | Python Equivalent |
|---|---|
| R 1-based indexing | Python 0-based indexing throughout |
| `list(a=1, b=2)` (named list) | `dict` |
| `missing(arg)` | Module-level `_MISSING = object()` sentinel |
| `match(x, table, 0L)` | Dict-based lookup; 0 or -1 for not found |
| `rep(x, n)` | `[x] * n` or `np.repeat` |
| `rbind` / `cbind` | `np.vstack` / `np.column_stack` or `np.hstack` |
| `apply(m, 1, paste, collapse=sep)` | List comprehension with `str.join` over rows |
| `cumsum(c(...))` | `np.cumsum(np.concatenate([...]))` |
| `pmax` / `pmin` | `np.maximum` / `np.minimum` |
| `outer(x, y, FUN)` | NumPy broadcasting |
| `tapply(wt, factor(y), sum)` | `pd.Series.groupby(pd.Categorical).sum()` |
| `factor` / `levels` | `pd.Categorical` |
| `model.frame` / `model.matrix` | patsy/pandas equivalents or `NotImplementedError` stub |
| `attr(x, "terms")` | `x.attrs.get("terms")` |
| R graphics (`plot`, `polygon`, `text`, etc.) | matplotlib equivalents |
| `.Call("C_rpart")` | `from r2py_rpart import rpart as _C_rpart` |
| `.Call("C_pred_rpart")` | `from r2py_rpart import pred_rpart as _C_pred_rpart` |
| `.Call("C_xpred")` | `from r2py_rpart import xpred as _C_xpred` |
| `.Call("C_rpartexp2")` | `from r2py_rpart import rpartexp2 as _C_rpartexp2` |
| `.Call("C_init_rpcallback")` | `from r2py_rpart import init_rpcallback as _C_init_rpcallback` |
| `storage.mode(X) <- "double"` | `X = X.astype(np.float64)` |
| `t(Y)` (transpose for C call) | `Y.T.ravel()` (row-major flatten of transposed matrix) |
| R column-major matrix reshape | `np.reshape(..., order='F')` |
| `UseMethod(...)` | Direct dispatch stub returning `NotImplementedError` |
| `new.env()` / `assign()` / `get()` | Python `dict` |
| `pmatch` | Prefix-matching helper; returns 1-based index |
| `asNamespace("rpart")` + `environment<-` | No-op in Python; skipped |

**Notable per-file decisions:**

- **`rpartco.R / compress`**: `compress` is defined as a nested recursive function inside `rpartco` in R. Converted as a standalone Python function with closure variables (`is_leaf`, `nspace`) passed as explicit parameters.
- **`rpart.exp.R / drate2`**: Similarly nested inside `rpart.exp`; extracted as a standalone helper.
- **`rpart.R / tfun`**: Defined inline inside the `rpart` function body; converted as both a standalone function (`tfun.json`) and redefined inline within `rpart.json`.
- **`rpart.R / rpart`**: The largest function (~300 lines). Key complexity: ordered-factor categorical split matrix construction (`nadd > 0` branch), classification probability vector normalization (`method.int == 3` branch), and assembly of the final `ans` dict (replacing R's S3 `class(ans) <- "rpart"` with `ans["_rpart_class"] = "rpart"` and `ans["_xlevels"]` / `ans["_ylevels"]` for `attr()`-stored metadata).
- **`xpred.rpart.R`**: Cross-validation prediction wrapper. `sample(rep(1:xval, length.out=nobs), nobs, replace=FALSE)` → `np.random.permutation(np.resize(np.arange(1, xval+1), nobs))`. `array(pred, dim=c(numresp, len(cp), nrow(X)))` + `aperm(temp)` → `pred.reshape((numresp, n_cp, nrow_X), order='F')` followed by `np.transpose(temp)`. `matrix(pred, nrow=nrow(X), byrow=TRUE)` → `pred.reshape((nrow_X, n_cp), order='C')`.
- **`text.rpart.R / oval`**: R's `polygon(x, y)` → `ax.fill(x, y)` (matplotlib filled polygon via `Axes` object).
- **`snip.rpart.mouse.R`**: Interactive R function using `identify()`; converted as a stub raising `NotImplementedError` since terminal interaction is not reproducible in Python.
- **`post.rpart.R`**: PostScript tree export using R's `postscript()` device; converted using `matplotlib.backends.backend_ps.FigureCanvasPS` with a `PdfPages`-like context manager stub.

---

### 3. Key Findings & Results

#### 3.1 Conversion Metrics

| Metric | Value |
|---|---|
| Total R files discovered | 36 |
| JSON dependency maps found | 36 |
| Skipped (no JSON) | 0 |
| Attempted | 36 |
| Succeeded | 36 |
| Failed | 0 |
| Total functions converted | 47 |

#### 3.2 Output Structure

All output written to `conversion_results/R/`, one subdirectory per R file, one JSON per function:

```
conversion_results/R/
├── formatg.R/formatg.json
├── importance.R/importance.json
├── labels.rpart.R/labels.rpart.json
├── meanvar.rpart.R/meanvar.rpart.json, meanvar.json
├── model.frame.rpart.R/model.frame.rpart.json
├── na.rpart.R/na.rpart.json
├── path.rpart.R/path.rpart.json
├── plotcp.R/plotcp.json
├── plot.rpart.R/plot.rpart.json
├── post.R/post.json
├── post.rpart.R/post.rpart.json
├── predict.rpart.R/predict.rpart.json
├── pred.rpart.R/pred.rpart.json
├── printcp.R/printcp.json
├── print.rpart.R/print_rpart.json
├── prune.R/prune.json
├── prune.rpart.R/prune_rpart.json
├── residuals.rpart.R/residuals.rpart.json
├── roc.rpart.R/ss.compare.json, roc.rpart.json
├── rpart.anova.R/rpart.anova.json
├── rpart.branch.R/rpart.branch.json
├── rpartcallback.R/rpartcallback.json
├── rpart.class.R/rpart.class.json
├── rpart.control.R/rpart.control.json
├── rpartco.R/compress.json, rpartco.json
├── rpart.exp.R/drate2.json, rpart.exp.json
├── rpart.matrix.R/rpart.matrix.json
├── rpart.poisson.R/rpart.poisson.json
├── rpart.R/tfun.json, rpart.json
├── rsq.rpart.R/rsq.rpart.json
├── snip.rpart.mouse.R/snip_rpart_mouse.json
├── snip.rpart.R/snip_rpart.json
├── summary.rpart.R/summary.rpart.json
├── text.rpart.R/oval.json, rectangle.json, text.rpart.json
├── xpred.rpart.R/xpred.rpart.json
└── zzz.R/tree.depth.json, descendants.json, node.match.json,
         string.bounding.box.json, on_unload.json
```

#### 3.3 Technical Insights

- **C extension boundary**: All five `.Call()` entry points (`C_rpart`, `C_pred_rpart`, `C_xpred`, `C_rpartexp2`, `C_init_rpcallback`) were consistently mapped to `r2py_rpart` module imports, preserving the Python-to-C interface contract established in earlier phases.
- **Column-major vs. row-major**: R's default column-major matrix layout required systematic use of `order='F'` in numpy reshape operations for any matrix constructed from C output or passed to C functions.
- **`eval.parent(model.frame(...))` is a hard boundary**: This R pattern—dynamically constructing a `model.frame` call from the parent call object—cannot be faithfully reproduced in Python without a formula parser. Consistently resolved with `NotImplementedError` stubs to be filled in once patsy integration is available.
- **`asNamespace` / `environment<-`**: R's namespace pinning for init-function closures (to prevent garbage collection issues) has no Python equivalent and was safely omitted.

---

### 4. Conclusion & Next Steps

All 36 R source files in `rpart/R/` have been successfully converted to Python, producing 47 JSON function definitions in `conversion_results/R/`. The conversion pipeline is complete for Phase 10.1.

Suggested next steps:
1. **Assemble Python modules**: Collect JSON outputs into `.py` module files, resolving imports between converted functions.
2. **Formula/model.frame integration**: Implement the patsy-based `model.frame` equivalent to replace `NotImplementedError` stubs in `rpart`, `xpred.rpart`, and `model.frame.rpart`.
3. **C extension linkage validation**: Verify that the `r2py_rpart` module correctly exposes all five C entry points (`rpart`, `pred_rpart`, `xpred`, `rpartexp2`, `init_rpcallback`) with the parameter signatures assumed by the converted wrappers.
4. **Test generation**: Run `/generate-python-function-tests` for the converted functions to benchmark output against the original R implementations.
