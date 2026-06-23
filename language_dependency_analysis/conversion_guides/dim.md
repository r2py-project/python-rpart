# Conversion Guide: `dim` (R to Python)

---

## 1. Overview of `dim` in R

`dim(x)` is a base R primitive that retrieves the **dimensions** of an object as an integer vector. Its behaviour varies by object type:

| Input type | Return value |
|---|---|
| Matrix (2-D array) | Integer vector of length 2: `c(nrow, ncol)` |
| N-dimensional array | Integer vector of length N |
| Data frame | Integer vector of length 2: `c(nrow, ncol)` |
| Vector / scalar | `NULL` (no dimension attribute set) |
| `NULL` | `NULL` |

Key properties:
- Indexing into the result with `[1L]` yields the number of rows; `[2L]` yields the number of columns (R uses 1-based indexing).
- When the argument is `NULL` (e.g. `fit$csplit` may be absent), `dim()` returns `NULL` and the caller is responsible for handling that case.
- The function is vectorised over the object's attribute, not over a collection of objects.

---

## 2. Contextual Usage Analysis

The CSV references two source files. Both files apply `dim` to 2-D objects (matrices and data frames) and use the results as integer metadata passed either to a C routine or to control array-padding logic.

### `pred.rpart.R` — lines 17–20

`dim` is called on four objects and the results are immediately wrapped in `as.integer(...)` before being forwarded to the C function `C_pred_rpart`:

| Call | Object | What is retrieved |
|---|---|---|
| `dim(x)` | Predictor matrix `x` (numeric matrix, rows = observations, cols = features) | `c(nrow, ncol)` — full shape |
| `dim(frame)[1L]` | `fit$frame` data frame (one row per tree node) | Number of tree nodes |
| `dim(fit$splits)` | `fit$splits` matrix (one row per split) | `c(nrow, ncol)` — full shape |
| `dim(fit$csplit)` | `fit$csplit` matrix **or** `NULL` | `c(nrow, ncol)` or handled via `if (is.null(...)) rep(0L, 2L)` |

Pattern: retrieve the full shape vector (or a single dimension) and pass it as a length-2 or length-1 integer array to a C extension.

### `roc.rpart.R` — lines 15–16 and 21–22

`dim` is called on `pred.np`, a boolean matrix produced by `outer()`. Only individual dimensions are used:

```r
last.r <- dim(pred.np)[1L]   # number of rows
last.c <- dim(pred.np)[2L]   # number of columns
```

This pair appears **twice**: once before a possible `rbind` that prepends a row, and once after, to refresh `last.r` / `last.c` with the updated shape.

Pattern: extract row and column counts from a 2-D boolean matrix and use them as loop/index bounds.

---

## 3. Python Conversion Strategy

**Primary library: NumPy (`numpy`).**

NumPy's `ndarray` stores shape information in its `.shape` attribute, which returns a tuple of integers directly analogous to R's `dim()` result. Because all objects in both files are 2-D arrays or matrices:

- `dim(x)` → `x.shape` (tuple of all dimensions)
- `dim(x)[1L]` → `x.shape[0]` (row count; Python is 0-based)
- `dim(x)[2L]` → `x.shape[1]` (column count)
- `dim(x)` passed as an integer pair → `np.array(x.shape, dtype=np.int32)`

For `pandas.DataFrame` objects (the natural Python analogue of an R data frame), `.shape` behaves identically, so the translation is uniform regardless of whether the object is a NumPy array or a DataFrame.

`math` / plain Python `len()` are **not** preferred because the objects are multi-dimensional; `.shape` is the idiomatic, zero-overhead way to obtain dimensions from any NumPy array or Pandas DataFrame.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Retrieving the full shape of a 2-D object

**Locations:** `pred.rpart.R` — function `pred.rpart`, lines 17 and 19 (`dim(x)`, `dim(fit$splits)`)

**Original R context**

`x` is a numeric matrix (rows = observations, columns = predictor variables). `fit$splits` is a numeric matrix (rows = splits, columns = split attributes). Both objects always have exactly two dimensions. The full shape vector is passed as a length-2 integer array to a C routine.

```r
# R — generalised snippet
as.integer(dim(x))          # -> c(nrow, ncol) as integer vector
as.integer(dim(fit$splits)) # -> c(nrow, ncol) as integer vector
```

**Python equivalent**

```python
import numpy as np

# x is a 2-D np.ndarray (observations x predictors)
# splits is a 2-D np.ndarray (splits x attributes)

dim_x      = np.array(x.shape, dtype=np.int32)       # [nrow, ncol]
dim_splits = np.array(splits.shape, dtype=np.int32)   # [nrow, ncol]
```

**Explanation**

`ndarray.shape` is a plain Python tuple of ints, so `np.array(x.shape, dtype=np.int32)` produces a 1-D integer array equivalent to R's `as.integer(dim(x))`. No loop or special call is required; NumPy exposes shape as a constant-time attribute lookup.

---

### 4.2 Retrieving a single dimension (row count) from a data frame

**Locations:** `pred.rpart.R` — function `pred.rpart`, line 18 (`dim(frame)[1L]`)

**Original R context**

`frame` is `fit$frame`, a data frame with one row per tree node. Only the row count is needed.

```r
# R — generalised snippet
as.integer(dim(frame)[1L])  # number of rows in the frame data frame
```

**Python equivalent**

```python
import numpy as np
import pandas as pd

# frame is a pandas DataFrame with one row per tree node
n_nodes = np.int32(frame.shape[0])   # shape[0] == number of rows
# or equivalently for a plain ndarray:
# n_nodes = np.int32(frame_array.shape[0])
```

**Explanation**

R's 1-based index `[1L]` selects the first element of the `dim` vector (number of rows). Python's 0-based index `shape[0]` is the direct equivalent. Both `pandas.DataFrame.shape` and `numpy.ndarray.shape` follow the same `(nrows, ncols, ...)` convention.

---

### 4.3 Handling a potentially NULL object with a fallback

**Locations:** `pred.rpart.R` — function `pred.rpart`, line 20 (`dim(fit$csplit)`)

**Original R context**

`fit$csplit` may be absent (`NULL`) when there are no categorical splits. The R code guards against this explicitly:

```r
# R — generalised snippet
as.integer(
    if (is.null(fit$csplit)) rep(0L, 2L) else dim(fit$csplit)
)
# Returns c(0L, 0L) when csplit is absent, c(nrow, ncol) otherwise
```

**Python equivalent**

```python
import numpy as np

# csplit is either None or a 2-D np.ndarray
if csplit is None:
    dim_csplit = np.zeros(2, dtype=np.int32)          # [0, 0]
else:
    dim_csplit = np.array(csplit.shape, dtype=np.int32)  # [nrow, ncol]
```

**Explanation**

R's `NULL` maps to Python's `None`. The guard `is.null(fit$csplit)` becomes `csplit is None`. When the object is present, `csplit.shape` returns the 2-element shape tuple, mirroring `dim(fit$csplit)`. The fallback produces a zero-filled integer array of length 2, matching `rep(0L, 2L)`.

---

### 4.4 Extracting row and column counts for bounds checking and conditional padding

**Locations:** `roc.rpart.R` — function `roc.rpart`, lines 15–16 and 21–22

**Original R context**

`pred.np` is a 2-D boolean matrix produced by `outer()`. Its row and column counts are captured before and after a conditional `rbind` that may prepend an extra row.

```r
# R — generalised snippet (first occurrence, lines 15-16)
last.r <- dim(pred.np)[1L]   # row count
last.c <- dim(pred.np)[2L]   # column count

if (sum(pred.np[1L, ]) > 0L) {
    pred.np <- rbind(matrix(FALSE, nrow = 1L, ncol = last.c), pred.np)
    cutoffs  <- c(NA, cutoffs)
}

# R — generalised snippet (second occurrence, lines 21-22)
last.r <- dim(pred.np)[1L]   # refresh after possible rbind
last.c <- dim(pred.np)[2L]   # refresh after possible rbind
```

**Python equivalent**

```python
import numpy as np

# pred_np is a 2-D boolean np.ndarray produced by np.greater_equal.outer or
# np.subtract.outer / broadcasting equivalent of R's outer()

# First occurrence
last_r, last_c = pred_np.shape   # unpack both dimensions at once

if pred_np[0, :].sum() > 0:
    extra_row = np.zeros((1, last_c), dtype=bool)
    pred_np   = np.vstack([extra_row, pred_np])
    cutoffs   = np.concatenate([[np.nan], cutoffs])

# Second occurrence — refresh after possible vstack
last_r, last_c = pred_np.shape
```

**Explanation**

- `dim(pred.np)[1L]` and `dim(pred.np)[2L]` (R, 1-based) become `pred_np.shape[0]` and `pred_np.shape[1]` (Python, 0-based). Tuple unpacking (`last_r, last_c = pred_np.shape`) is idiomatic Python and retrieves both values in one step.
- R's `rbind(matrix(FALSE, ...), pred.np)` is replaced by `np.vstack([extra_row, pred_np])`.
- R's `pred.np[1L, ]` (first row, 1-based) becomes `pred_np[0, :]` (first row, 0-based).
- After any structural modification (`vstack`), `.shape` reflects the updated array dimensions automatically — no separate re-query is needed beyond re-reading the attribute.
