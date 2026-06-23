# Conversion Guide: `nrow` (R to Python)

---

## 1. Overview of `nrow` in R

`nrow(x)` returns the number of rows of a matrix, data frame, or array. It is one of R's fundamental dimension-querying functions.

- **Input:** A matrix, data frame, or multi-dimensional array `x`.
- **Output:** A single integer giving the row count, or `NULL` if `x` has no row dimension (e.g., is a plain vector or `NULL`).
- **Typical use:** Capturing the number of observations in a data frame, the number of splits in a matrix, or the number of nodes in an rpart frame object — all of which then drive loop bounds, conditional checks, allocation sizes, and index generation.

`nrow(x)` is exactly equivalent to `dim(x)[1]` for objects that have a `dim` attribute. For a plain R vector (no `dim`), `nrow` returns `NULL`, whereas `length` returns the element count.

---

## 2. Contextual Usage Analysis

Across the 21 CSV entries in the rpart package, `nrow` is applied to three broad categories of R objects:

| Object type | Representative call | Role |
|---|---|---|
| **Data frame** | `nrow(x$frame)`, `nrow(ff)`, `nrow(frame)`, `nrow(m)` | Count tree nodes or model-frame observations |
| **Matrix** | `nrow(X)`, `nrow(rpfit$isplit)`, `nrow(rpfit$csplit)`, `nrow(rpfit$cptable)`, `nrow(x$splits)`, `nrow(x$csplit)`, `nrow(cs)`, `nrow(y)` | Count observations or split table rows |
| **Guard / branch condition** | `nrow(x$frame) <= 1L`, `nrow(frame) == 1L`, `nrow(x$csplit)` | Early-exit checks or conditional logic |

The return value is always used as a plain integer scalar — never as a vector. The common patterns are:

1. **Assign to a variable** used for further arithmetic or as a loop bound:
   `n <- nrow(ff)`, `nobs <- nrow(X)`, `nsplit <- nrow(rpfit$isplit)`
2. **Use inline in a conditional guard:**
   `if (nrow(x$frame) <= 1L) stop(...)`, `if (nrow(frame) == 1L) return(...)`
3. **Use inline to build an index range or sequence:**
   `1L:nrow(x$csplit)`, `-(nrow(frame) + 1L)`
4. **Pass directly to another function:**
   `matrix(temp, nrow = nrow(x))` (re-shaping a vector back to matrix dimensions)

All objects (`frame`, `X`, `splits`, `csplit`, `cptable`, model frame `m`, survival matrix `y`) are 2-D structures in Python as well — either `pandas.DataFrame` or `numpy.ndarray` — so the translation is direct.

---

## 3. Python Conversion Strategy

**Primary equivalent:** `len(df)` for `pandas.DataFrame` objects and `arr.shape[0]` for `numpy.ndarray` objects.

Rationale:
- In Python/pandas, `len(df)` returns the number of rows of a DataFrame, which is the idiomatic form and mirrors R's `nrow(df)` exactly.
- For numpy arrays and matrices, `.shape[0]` accesses the first dimension directly.
- Because `nrow` always returns a scalar integer, neither vectorisation nor broadcasting is involved; `numpy` is not needed for the `nrow` call itself. However, the arrays it is called on are typically numpy arrays or pandas DataFrames created elsewhere in the converted code.
- `numpy.ndarray.shape[0]` and `len(pandas.DataFrame)` are O(1) attribute lookups — no iteration over data — matching R's behaviour.

**Do not use** `numpy.size` (returns total element count) or `df.shape` alone (returns a tuple, not a scalar) as direct replacements.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Counting rows of a data frame and assigning to a variable

**Locations:**
- `labels.rpart.R` — `labels.rpart`, line 27: `n <- nrow(ff)`
- `rpart.exp.R` — `rpart.exp`, line 18: `n <- nrow(y)`

**Original R Context:**

`ff` and `y` are a data frame and a matrix respectively. The result is a scalar integer used downstream as a length or bound.

```r
# labels.rpart.R
ff <- object$frame          # data frame
n <- nrow(ff)               # integer scalar: number of tree nodes
if (n == 1L) return("root")

# rpart.exp.R
ny <- ncol(y)               # y is a Surv matrix (n_obs x 2 or 3)
n <- nrow(y)                # integer scalar: number of observations
status <- y[, ny]
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

# --- labels.rpart equivalent ---
ff = object_frame          # pandas.DataFrame: the rpart frame
n = len(ff)                # number of tree nodes
if n == 1:
    return "root"

# --- rpart.exp equivalent ---
# y is a numpy.ndarray of shape (n_obs, 2) or (n_obs, 3)
ny = y.shape[1]            # number of columns
n = y.shape[0]             # number of observations
status = y[:, ny - 1]
```

**Explanation:**
- `nrow(df)` → `len(df)` for a pandas DataFrame (returns an `int`).
- `nrow(mat)` → `mat.shape[0]` for a numpy ndarray.
- Both return a plain Python `int`, matching the scalar integer R returns.

---

### 4.2 Inline guard: early exit when the tree has only a root node

**Locations:**
- `plot.rpart.R` — `plot.rpart`, line 6: `if (nrow(x$frame) <= 1L) stop(...)`
- `text.rpart.R` — `text.rpart`, line 12: `if (nrow(x$frame) <= 1L) stop(...)`
- `pred.rpart.R` — `pred.rpart`, line 6: `if (nrow(frame) == 1L) return(...)`

**Original R Context:**

```r
# plot.rpart.R / text.rpart.R
if (nrow(x$frame) <= 1L)
    stop("fit is not a tree, just a root")

# pred.rpart.R
frame <- fit$frame
if (nrow(frame) == 1L)          # root-only tree
    return(structure(rep(1, nrow(x), names = rownames(x))))
```

**Python Equivalent:**

```python
# plot / text equivalent
if len(x_frame) <= 1:
    raise ValueError("fit is not a tree, just a root")

# pred.rpart equivalent
frame = fit["frame"]            # pandas.DataFrame
if len(frame) == 1:             # root-only tree
    return pd.Series(
        np.ones(x.shape[0]), index=x.index, dtype=float
    )
```

**Explanation:**
- R's `stop(...)` maps to Python's `raise ValueError(...)`.
- R's `return(structure(rep(1, nrow(x), names = rownames(x))))` maps to returning a pandas `Series` of ones indexed by `x.index`.
- `nrow(frame)` → `len(frame)` because `frame` is a DataFrame.

---

### 4.3 Counting observation rows and column count of a feature matrix

**Locations:**
- `rpart.R` — `rpart`, line 32: `nobs <- nrow(X)`
- `pred.rpart.R` — `pred.rpart`, line 7: `nrow(x)` (inside `rep(1, nrow(x), ...)`)
- `pred.rpart.R` — `pred.rpart`, line 11: `-(nrow(frame) + 1L)`
- `xpred.rpart.R` — `xpred.rpart`, lines 48, 71, 137, 141: `nrow(X)`

**Original R Context:**

`X` is the predictor matrix (observations × variables). `nrow(X)` gives the observation count, used as a dimension argument to `.Call`, to build vectors, or to create output matrices.

```r
# rpart.R
X <- rpart.matrix(m)
nobs <- nrow(X)             # number of observations
nvar <- ncol(X)

# pred.rpart.R
frame$index <- 1L + c(0L, cumsum(...))[-(nrow(frame) + 1L)]

# xpred.rpart.R
nobs <- nrow(X)
# ... later ...
matrix(pred, nrow = nrow(X), byrow = TRUE,
       dimnames = list(rownames(X), format(cp)))
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# rpart equivalent
X = rpart_matrix(m)         # numpy.ndarray, shape (n_obs, n_var)
nobs = X.shape[0]           # number of observations
nvar = X.shape[1]

# pred.rpart frame index equivalent
cumulative = np.cumsum(...)
frame_index = np.concatenate([[0], cumulative])[:-(len(frame) + 1)] + 1

# xpred.rpart output matrix equivalent
nobs = X.shape[0]
# ... after calling C routine and getting flat pred array ...
result = pd.DataFrame(
    pred.reshape(nobs, -1, order="C"),
    index=list(X.index) if hasattr(X, "index") else None,
    columns=[format(v) for v in cp]
)
```

**Explanation:**
- `nrow(X)` → `X.shape[0]` for a numpy array.
- R's `matrix(pred, nrow = nrow(X), byrow = TRUE)` maps to `pred.reshape(nobs, -1, order="C")` since `byrow = TRUE` means values fill the matrix row-by-row, which corresponds to C (row-major) order.
- R's negative index `[-(nrow(frame) + 1L)]` — which drops the last element — becomes Python slice `[:-(len(frame) + 1)]`.

---

### 4.4 Counting rows of the model frame

**Locations:**
- `rpart.R` — `rpart`, line 29: `nrow(m)`

**Original R Context:**

`m` is the model frame returned by `stats::model.frame`. `nrow(m)` gives the number of complete observations used to build the tree.

```r
m <- eval.parent(temp)      # model frame: a data frame
if (!length(wt)) wt <- rep(1, nrow(m))
```

**Python Equivalent:**

```python
# m is a pandas DataFrame (the model frame)
if wt is None or len(wt) == 0:
    wt = np.ones(len(m))
```

**Explanation:**
- `nrow(m)` → `len(m)` because the model frame is a DataFrame.
- R's `rep(1, nrow(m))` → `np.ones(len(m))`.

---

### 4.5 Counting rows of split result matrices

**Locations:**
- `rpart.R` — `rpart`, line 173: `nsplit <- nrow(rpfit$isplit)`
- `rpart.R` — `rpart`, line 175: `ncat <- nrow(rpfit$csplit)` (conditional)
- `rpart.R` — `rpart`, line 180: `nrow(rpfit$cptable)`
- `rpart.R` — `rpart`, line 213: `nrow(cs)`
- `summary.rpart.R` — `summary.rpart`, line 44: `nrow(x$splits)`
- `snip.rpart.R` — `snip.rpart`, line 58: `nrow(x$csplit)`

**Original R Context:**

These are all matrices returned from the C routine `C_rpart` or stored on the fitted object. Their row counts determine how many splits of each type were found.

```r
# rpart.R
nsplit <- nrow(rpfit$isplit)        # total splits (primary + surrogate)
ncat   <- if (!is.null(rpfit$csplit)) nrow(rpfit$csplit) else 0L
numcp  <- ncol(rpfit$cptable)       # number of cp values (cols, not rows)
temp   <- if (nrow(rpfit$cptable) == 3L) ...  # 3 or 5 row names

# rpart.R — ordered factor handling
cs  <- rpfit$csplit
ncs <- ncol(cs); ncc <- ncol(newc)
if (ncs < ncc) cs <- cbind(cs, matrix(0L, nrow(cs), ncc - ncs))

# snip.rpart.R
if (is.matrix(x$csplit)) split[temp, 4L] <- 1L:nrow(x$csplit)

# summary.rpart.R
cuts <- character(nrow(x$splits))
```

**Python Equivalent:**

```python
import numpy as np

# rpart equivalent
isplit = rpfit["isplit"]            # numpy.ndarray
csplit = rpfit.get("csplit")        # numpy.ndarray or None
cptable = rpfit["cptable"]         # numpy.ndarray

nsplit = isplit.shape[0]           # total number of splits
ncat   = csplit.shape[0] if csplit is not None else 0

# cptable row count check (3 rows = no xval, 5 rows = with xval)
if cptable.shape[0] == 3:
    temp_names = ["CP", "nsplit", "rel error"]
else:
    temp_names = ["CP", "nsplit", "rel error", "xerror", "xstd"]

# ordered factor column padding (rpart.R line 213 context)
cs  = rpfit["csplit"]              # numpy.ndarray
ncs = cs.shape[1]
ncc = newc.shape[1]
if ncs < ncc:
    cs = np.hstack([cs, np.zeros((cs.shape[0], ncc - ncs), dtype=np.int32)])

# snip.rpart equivalent
if isinstance(x_csplit, np.ndarray) and x_csplit.ndim == 2:
    split[temp, 3] = np.arange(1, x_csplit.shape[0] + 1)   # 0-based col index 3 = R col 4

# summary.rpart equivalent
x_splits = x["splits"]             # numpy.ndarray
cuts = [""] * x_splits.shape[0]
```

**Explanation:**
- `nrow(mat)` → `mat.shape[0]` for all numpy matrices returned from C routines.
- R's `character(nrow(x$splits))` → `[""] * x_splits.shape[0]` (a list of empty strings).
- R's `1L:nrow(x$csplit)` produces `[1, 2, ..., nrow]` (1-based); Python equivalent is `np.arange(1, x_csplit.shape[0] + 1)`.
- R column index `4L` (1-based) becomes Python column index `3` (0-based).

---

### 4.6 Reshaping a flat vector back into a matrix (preserving row count)

**Locations:**
- `formatg.R` — `formatg`, line 9: `matrix(temp, nrow = nrow(x))`

**Original R Context:**

`x` is a numeric matrix. `sprintf` flattens it to a character vector `temp`; the result is reshaped back to the original matrix dimensions.

```r
formatg <- function(x, digits = getOption("digits"),
                    format = paste0("%.", digits, "g"))
{
    if (!is.numeric(x)) stop("'x' must be a numeric vector")
    temp <- sprintf(format, x)
    if (is.matrix(x)) matrix(temp, nrow = nrow(x)) else temp
}
```

`x` is a numeric matrix; `temp` is a flat character vector of the same total length. `matrix(temp, nrow = nrow(x))` fills by column (R default), reconstructing the original shape.

**Python Equivalent:**

```python
import numpy as np

def formatg(x, digits=None, fmt=None):
    """Format numeric array using C's 'g' format."""
    if digits is None:
        digits = 6   # default significant digits
    if fmt is None:
        fmt = f".{digits}g"

    x = np.asarray(x)
    # Apply format element-wise
    temp = np.vectorize(lambda v: format(v, fmt))(x)

    # If x was 2-D, return same shape; otherwise return flat array
    if x.ndim == 2:
        return temp.reshape(x.shape, order="F")  # column-major to match R
    return temp
```

**Explanation:**
- R's `matrix(temp, nrow = nrow(x))` fills the matrix **column-by-column** (Fortran / column-major order), so the Python reshape must use `order="F"`.
- `nrow(x)` → `x.shape[0]` in numpy; but since the full shape is already known via `x.shape`, the reshape uses `x.shape` directly rather than `x.shape[0]` alone.
- `np.vectorize` applies the format string element-wise across the array.

---

## Summary Table

| R expression | Python equivalent | Notes |
|---|---|---|
| `nrow(df)` | `len(df)` | `df` is `pandas.DataFrame` |
| `nrow(arr)` | `arr.shape[0]` | `arr` is `numpy.ndarray` |
| `n <- nrow(x)` | `n = len(x)` or `n = x.shape[0]` | scalar integer result |
| `if (nrow(x) == 1L)` | `if len(x) == 1:` | guard condition |
| `if (nrow(x) <= 1L)` | `if len(x) <= 1:` | guard condition |
| `rep(1, nrow(x))` | `np.ones(len(x))` or `np.ones(x.shape[0])` | vector of ones |
| `matrix(v, nrow = nrow(x))` | `v.reshape(x.shape, order="F")` | column-major fill |
| `1L:nrow(x)` | `np.arange(1, x.shape[0] + 1)` | 1-based integer sequence |
| `-(nrow(x) + 1L)` | `-(len(x) + 1)` | negative index for slicing |
| `matrix(0L, nrow(cs), k)` | `np.zeros((cs.shape[0], k), dtype=np.int32)` | zero-padding |
