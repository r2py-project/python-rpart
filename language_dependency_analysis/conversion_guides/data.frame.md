# Conversion Guide: `data.frame` in R

---

## 1. Overview of `data.frame` in R

`data.frame()` is R's primary built-in constructor for creating a two-dimensional, heterogeneous tabular data structure. Each column can hold a different data type (numeric, character, integer, logical, factor, etc.), and all columns must have the same number of rows. It is the standard representation for datasets in R — analogous to a database table or a spreadsheet.

**Signature:**
```r
data.frame(..., row.names = NULL, check.rows = FALSE, check.names = TRUE,
           fix.empty.names = TRUE, stringsAsFactors = FALSE)
```

Key behaviours relevant to the rpart usages:

- **Named columns:** Arguments passed as `name = value` become columns with that name. Bare symbols (e.g., `tpcp`) are promoted to columns whose name is taken from the symbol itself.
- **`row.names`:** An optional vector (or scalar integer/character for a single-row frame) that labels each row. When a scalar integer `1L` is supplied the resulting frame has a single row labelled `"1"`.
- **Recycling:** Scalar values (e.g., `0L`, `"<leaf>"`) are recycled to the length of the longest column vector, in the same way as R's general recycling rule.
- **Return value:** An object of class `"data.frame"` — a list of equal-length vectors with additional attributes (`names`, `row.names`, `class`).

---

## 2. Contextual Usage Analysis

Three distinct calls to `data.frame()` appear across two R source files.

### Usage in `roc.rpart.R` (line 71)

The function `roc.rpart` builds a ROC analysis table. After iterating over cutoff values and populating column-vector matrices (`sensitivity`, `specificity`, `pospred`, `negpred`, `tpcp`, `tncp`, `tpcn`, `tncn`), it assembles them into a single return value via `data.frame()`.

- The numeric columns (`tpcp`, `tncp`, `tpcn`, `tncn`) are `cutoff.n × 1` matrices produced by accumulating scalar assignments inside a loop.
- The string columns (`cutoffs`, `sensitivity`, `specificity`, `pospred`, `negpred`) are produced by formatting rounded numeric values with `format(round(...))`, yielding character vectors/matrices of length `cutoff.n`.
- The result is returned directly as the function's return value — a mixed-type table with `cutoff.n` rows.

### Usages in `rpart.R` (lines 221 and 233)

The `rpart` function builds the `frame` component of the fitted rpart object. There are two branches depending on whether any splits were found:

**No-split branch (line 221):**  
The tree has only a root node. All vector columns (`n`, `wt`, `dev`, `yval`, `complexity`) are extracted from the first row of C-level output arrays (`rpfit$inode`, `rpfit$dnode`). Scalar integers `0L` are used for `ncompete` and `nsurrogate`, recycled to length 1. `row.names = 1L` produces a single-row frame with row label `"1"`. `var = "<leaf>"` is a length-1 character string.

**With-splits branch (line 233):**  
The tree has multiple nodes. Column vectors have length equal to the number of nodes. `row.names = rpfit$inode[, 1L]` labels each row with the node number. `var = tname[svar + 1L]` is a character vector of variable names. `ncompete` is computed with `pmax(0L, ...)` and `nsurrogate` directly from the inode matrix.

**Data types summary:**

| Column | Type | Source |
|---|---|---|
| `cutoffs` | character vector | `format(round(...))` |
| `tpcp`, `tncp`, `tpcn`, `tncn` | numeric matrix (n×1) | loop-accumulated scalars |
| `sensitivity`, `specificity`, `pospred`, `negpred` | character vector | `format(round(...))` |
| `var` | character (scalar or vector) | string constant or indexed `tname` |
| `n`, `wt`, `dev`, `yval`, `complexity` | numeric vector | columns of C output matrices |
| `ncompete`, `nsurrogate` | integer (scalar or vector) | scalar `0L` or `pmax`/direct extraction |
| `row.names` | integer scalar or integer vector | `1L` or `rpfit$inode[, 1L]` |

---

## 3. Python Conversion Strategy

The direct equivalent of R's `data.frame` in Python is **`pandas.DataFrame`**. The mapping is straightforward:

- `pd.DataFrame({...})` accepts a dict of `{column_name: array-like}` values, mirroring R's `data.frame(name = value, ...)` named-argument syntax.
- The `index` parameter of `pd.DataFrame` corresponds to R's `row.names`.
- Heterogeneous column types (mixed numeric and string) are natively supported.
- NumPy arrays and scalars can be passed directly as column values; scalars are broadcast across rows exactly as R recycles them.

`numpy` is used for all numeric column computations (the source arrays that feed into the `data.frame` call are already numpy arrays in the Python translation), so `pandas` is the natural and idiomatic finish step.

`math` module alternatives are not appropriate here because the column data are uniformly vector-valued (length equal to the number of cutoffs or the number of tree nodes).

---

## 4. Step-by-Step Conversion Examples

### 4.1 ROC summary table (`roc.rpart.R`, line 71)

**Locations:** `roc.rpart.R` — function `roc.rpart`

**Original R Context:**

All eight variables are vectors of length `cutoff.n`. `tpcp`, `tncp`, `tpcn`, `tncn` are `cutoff.n × 1` numeric matrices; the string columns are produced by `format(round(...))`. The result is the function's return value.

```r
# cutoffs, sensitivity, specificity, pospred, negpred are numeric vectors/matrices
# of length cutoff.n; tpcp/tncp/tpcn/tncn are numeric matrices (cutoff.n x 1)
data.frame(
    cutoffs     = format(round(cutoffs, 3L)),
    tpcp, tncp, tpcn, tncn,
    sensitivity = format(round(sensitivity, 2L)),
    specificity = format(round(specificity, 2L)),
    pospred     = format(round(pospred, 2L)),
    negpred     = format(round(negpred, 2L))
)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# cutoffs, tpcp, tncp, tpcn, tncn are 1-D numpy arrays of length cutoff_n
# sensitivity, specificity, pospred, negpred are 1-D numpy arrays of length cutoff_n

result = pd.DataFrame({
    "cutoffs":     [f"{v:.3f}" if not np.isnan(v) else "NA"
                    for v in np.round(cutoffs, 3)],
    "tpcp":        tpcp.ravel(),
    "tncp":        tncp.ravel(),
    "tpcn":        tpcn.ravel(),
    "tncn":        tncn.ravel(),
    "sensitivity": [f"{v:.2f}" for v in np.round(sensitivity.ravel(), 2)],
    "specificity": [f"{v:.2f}" for v in np.round(specificity.ravel(), 2)],
    "pospred":     [f"{v:.2f}" for v in np.round(pospred.ravel(), 2)],
    "negpred":     [f"{v:.2f}" for v in np.round(negpred.ravel(), 2)],
})
```

**Explanation:**

- `pd.DataFrame({name: array, ...})` is the direct equivalent of `data.frame(name = value, ...)`.
- R's `format(round(x, digits))` produces a right-aligned character string padded with spaces. In Python, `f"{v:.Nf}"` gives the same fixed-decimal string (without padding). If exact whitespace alignment is needed, `f"{v:>8.Nf}"` can be used.
- `tpcp` etc. are `(cutoff_n, 1)` shaped numpy arrays from the loop; `.ravel()` converts them to 1-D so `pandas` does not mis-interpret the shape.
- R's `NA` sentinel (for the boundary cutoff values) must be handled explicitly; numpy `np.nan` is the equivalent, and the conditional in the list comprehension emits `"NA"` as a string to match R's `format()` output.
- No `row.names` argument is used here; `pandas` assigns a default 0-based integer index, matching R's default sequential row numbering for this call.

---

### 4.2 Single-node tree frame (`rpart.R`, line 221)

**Locations:** `rpart.R` — function `rpart` (no-split branch)

**Original R Context:**

The tree produced no splits, so there is exactly one node. All node-level arrays contain a single row. `row.names = 1L` creates a single-row frame labelled `"1"`. `var`, `ncompete`, and `nsurrogate` are scalars recycled to length 1.

```r
# rpfit$inode and rpfit$dnode are matrices with 1 row (no-split case)
frame <- data.frame(
    row.names  = 1L,
    var        = "<leaf>",
    n          = rpfit$inode[, 5L],
    wt         = rpfit$dnode[, 3L],
    dev        = rpfit$dnode[, 1L],
    yval       = rpfit$dnode[, 4L],
    complexity = rpfit$dnode[, 2L],
    ncompete   = 0L,
    nsurrogate = 0L
)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# rpfit_inode and rpfit_dnode are 2-D numpy arrays; shapes (1, ...) in the no-split case.
# R uses 1-based column indexing; Python uses 0-based indexing, so column 5 -> index 4, etc.

frame = pd.DataFrame(
    {
        "var":        ["<leaf>"],
        "n":          rpfit_inode[:, 4],   # R col 5 -> Python index 4
        "wt":         rpfit_dnode[:, 2],   # R col 3 -> Python index 2
        "dev":        rpfit_dnode[:, 0],   # R col 1 -> Python index 0
        "yval":       rpfit_dnode[:, 3],   # R col 4 -> Python index 3
        "complexity": rpfit_dnode[:, 1],   # R col 2 -> Python index 1
        "ncompete":   [0],
        "nsurrogate": [0],
    },
    index=[1],   # row.names = 1L in R
)
```

**Explanation:**

- R's `row.names = 1L` sets the row label to the string `"1"` (a single-element row-names vector). In pandas this is expressed as `index=[1]`.
- R uses 1-based column indexing (`[, 5L]` means the fifth column). Python uses 0-based indexing, so `[, 5L]` becomes `[:, 4]`.
- Scalar values `0L` in R are recycled to match the number of rows. In Python, wrapping them in a list (`[0]`) is the idiomatic equivalent for a 1-row DataFrame.
- The string `"<leaf>"` must also be wrapped in a list so pandas treats it as a one-element column rather than trying to iterate over the characters.
- Column order in the resulting DataFrame matches R's, since Python dicts preserve insertion order (Python 3.7+).

---

### 4.3 Multi-node tree frame (`rpart.R`, line 233)

**Locations:** `rpart.R` — function `rpart` (with-splits branch)

**Original R Context:**

The tree has `num_nodes` internal/terminal nodes. All column arrays have length `num_nodes`. `row.names` is set to the node ID vector extracted from the C output. `var` is a character vector of split variable names; `ncompete` uses `pmax(0L, ...)` to clamp negative values.

```r
# num_nodes = nrow(rpfit$inode)
# svar is an integer vector of length num_nodes (split variable indices, 0-based w.r.t. tname)
# tname is a character vector: tname[0] = "<leaf>", tname[1..] = column names of X
frame <- data.frame(
    row.names  = rpfit$inode[, 1L],
    var        = tname[svar + 1L],       # R 1-based index into tname
    n          = rpfit$inode[, 5L],
    wt         = rpfit$dnode[, 3L],
    dev        = rpfit$dnode[, 1L],
    yval       = rpfit$dnode[, 4L],
    complexity = rpfit$dnode[, 2L],
    ncompete   = pmax(0L, rpfit$inode[, 3L] - 1L),
    nsurrogate = rpfit$inode[, 4L]
)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# rpfit_inode: 2-D numpy array, shape (num_nodes, ...)
# rpfit_dnode: 2-D numpy array, shape (num_nodes, ...)
# tname: Python list of strings, tname[0] = "<leaf>", tname[1..] = X column names
# svar: 1-D numpy integer array of length num_nodes

frame = pd.DataFrame(
    {
        "var":        [tname[i] for i in (svar + 1)],  # svar already 0-based offset
        "n":          rpfit_inode[:, 4],   # R col 5 -> index 4
        "wt":         rpfit_dnode[:, 2],   # R col 3 -> index 2
        "dev":        rpfit_dnode[:, 0],   # R col 1 -> index 0
        "yval":       rpfit_dnode[:, 3],   # R col 4 -> index 3
        "complexity": rpfit_dnode[:, 1],   # R col 2 -> index 1
        "ncompete":   np.maximum(0, rpfit_inode[:, 2] - 1),  # R col 3 -> index 2
        "nsurrogate": rpfit_inode[:, 3],   # R col 4 -> index 3
    },
    index=rpfit_inode[:, 0].astype(int),  # row.names = rpfit$inode[, 1L] -> index 0
)
```

**Explanation:**

- `row.names = rpfit$inode[, 1L]` extracts the node IDs (R column 1, index 0). In pandas this becomes `index=rpfit_inode[:, 0].astype(int)`.
- `tname[svar + 1L]` in R performs vectorised 1-based indexing into a character vector. In Python, `tname` is a list, and the equivalent is a list comprehension `[tname[i] for i in (svar + 1)]`. Note that R's `svar` is computed as `rpfit$isplit[temp, 1L]` which is already 1-based internally; the `+1` in `tname[svar + 1L]` accounts for the `"<leaf>"` sentinel at position 1 in R (position 0 in Python, so `svar + 1` in R becomes `svar` in Python if `svar` was already correctly 0-indexed, or `svar + 1` if `svar` retains R's 1-based origin — verify the upstream computation).
- R's `pmax(0L, x)` is the element-wise maximum clamping to zero. The numpy equivalent is `np.maximum(0, x)`.
- Column indexing: R uses 1-based column indices; Python uses 0-based. The mapping is `R col k -> Python index k-1` throughout.
- Integer dtype should be preserved for `ncompete` and `nsurrogate` if downstream code expects integer columns; `np.maximum` preserves the dtype of its inputs when both are integer arrays.
