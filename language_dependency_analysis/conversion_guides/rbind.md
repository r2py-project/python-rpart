# Conversion Guide: `rbind` in R

---

## 1. Overview of `rbind` in R

`rbind` (row-bind) concatenates matrices, vectors, or data frames **vertically** — stacking them row by row into a single combined object. It is R's primary mechanism for appending rows to an existing rectangular structure.

Key characteristics:

- **Inputs:** Two or more matrices, vectors, or data frames. Vectors are treated as single-row matrices. All arguments must have the same number of columns (or a compatible multiple thereof).
- **Output:** A matrix (when all inputs are matrices or vectors) or a data frame (when any input is a data frame), with the number of rows equal to the total number of rows across all arguments.
- **Type coercion:** When mixing types (e.g., logical and numeric), R coerces all elements to the most general type (logical -> integer -> double -> complex -> character).
- **NA rows:** Passing a bare `NA` as one of the arguments inserts an entire row of `NA` values and is commonly used as a "pen-lift" sentinel in plotting routines.
- **Dimension names:** Row names are taken from the arguments where available; column names are inherited from the first named argument.

---

## 2. Contextual Usage Analysis

The CSV entries cover three distinct source files and two functional contexts:

### Context A — Prepending / appending a sentinel row of uniform logical values (`roc.rpart.R`, lines 18 and 24)

`pred.np` is a 2-D logical matrix produced by `outer()` (rows = cutoffs, columns = leaf nodes). The two `rbind` calls act as bookends:

- **Line 18** prepends a row of all `FALSE` when the first row is not already all-`FALSE`, ensuring the ROC curve starts at (0, 0).
- **Line 24** appends a row of all `TRUE` when the last row is not already all-`TRUE`, ensuring the ROC curve ends at (1, 1).

Both arguments are logical (`matrix(FALSE, ...)` / `matrix(TRUE, ...)`), and the result is a logical matrix of the same type.

### Context B — Vertical concatenation of two integer matrices (`rpart.R`, line 214)

Inside `rpart()`, `cs` is an integer matrix from `rpfit$csplit` (possibly column-extended with `cbind`) and `newc` is a freshly built integer matrix encoding ordered-factor split directions. The `rbind(cs, newc)` call merges these two integer matrices into a single combined split-category matrix (`catmat`).

### Context C — Multi-argument row-bind of numeric vectors and `NA` for plot path construction (`rpart.branch.R`, lines 22–24)

`x` and `y` are numeric vectors holding the x- and y-coordinates of tree nodes. The function builds "horseshoe" polylines for `lines()` by stacking several coordinate slices plus a trailing `NA` (pen-lift) row:

```r
xx <- rbind(x[is.left], x[is.left] + temp,
            x[sibling] - temp, x[sibling], NA)
yy <- rbind(y[is.left], y[parent], y[parent], y[sibling], NA)
```

Each argument is a numeric vector of length equal to the number of left-child nodes; the `NA` inserts a full row of `NA`. The resulting matrices `xx` and `yy` each have 5 rows and as many columns as there are left children. They are returned as a list and later consumed by `lines()`.

### Recurring patterns

| Pattern | Files | Argument types |
|---|---|---|
| Prepend/append a uniform row | `roc.rpart.R` | logical matrix + `matrix(bool, 1, ncol)` |
| Concatenate two integer matrices | `rpart.R` | integer matrix + integer matrix |
| Stack numeric vectors + `NA` sentinel | `rpart.branch.R` | numeric vectors + scalar `NA` |

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

R's `rbind` is inherently a vectorized, array-level operation. `numpy.vstack` (or equivalently `numpy.concatenate(..., axis=0)`) is the direct functional analog: it accepts a sequence of arrays and stacks them along the first axis (rows), preserving dtypes unless coercion is needed. This matches R's behavior exactly for the matrix-on-matrix and vector-stacking cases.

For the `NA` sentinel pattern, `numpy` uses `np.nan` (a float64 sentinel) in place of R's `NA`. Because `np.nan` only exists in floating-point arrays, any integer array that needs a `nan` row must be cast to `float64` first — the same implicit coercion that R performs when mixing numeric and `NA`.

`pandas.DataFrame.append` / `pd.concat` is a valid alternative when working with data frames, but none of the CSV entries involve data frames — all results are matrices — so `numpy` is the most direct and efficient choice throughout.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Prepending / Appending a Uniform Logical Row (ROC boundary clamping)

**Locations:** `roc.rpart.R` — function `roc.rpart`, lines 18 and 24.

**Original R Context**

```r
# pred.np: logical matrix, shape (last.r, last.c)
# Prepend a row of FALSE if the first row is not all-FALSE
if (sum(pred.np[1L, ]) > 0L) {
    pred.np <- rbind(matrix(FALSE, nrow = 1L, ncol = last.c), pred.np)
    cutoffs <- c(NA, cutoffs)
}

# Append a row of TRUE if the last row is not all-TRUE
if (sum(pred.np[last.r, ]) < last.c) {
    pred.np <- rbind(pred.np, matrix(TRUE, nrow = 1L, ncol = last.c))
    cutoffs <- c(cutoffs, NA)
}
```

- `pred.np` is a `bool` matrix of shape `(last_r, last_c)`.
- `matrix(FALSE, nrow=1, ncol=last.c)` creates a `(1, last_c)` all-`False` row.
- `matrix(TRUE,  nrow=1, ncol=last.c)` creates a `(1, last_c)` all-`True` row.
- Return type: logical matrix (same dtype, one extra row added).

**Python Equivalent**

```python
import numpy as np

# pred_np: np.ndarray of dtype bool, shape (last_r, last_c)
last_r, last_c = pred_np.shape

# Prepend a row of False
if pred_np[0, :].sum() > 0:
    pred_np = np.vstack([np.zeros((1, last_c), dtype=bool), pred_np])
    cutoffs = np.concatenate([[np.nan], cutoffs])

last_r, last_c = pred_np.shape  # refresh after potential prepend

# Append a row of True
if pred_np[last_r - 1, :].sum() < last_c:
    pred_np = np.vstack([pred_np, np.ones((1, last_c), dtype=bool)])
    cutoffs = np.concatenate([cutoffs, [np.nan]])
```

**Explanation**

| R | Python | Notes |
|---|---|---|
| `matrix(FALSE, nrow=1, ncol=last.c)` | `np.zeros((1, last_c), dtype=bool)` | Both create a `(1, last_c)` all-`False` array |
| `matrix(TRUE,  nrow=1, ncol=last.c)` | `np.ones((1, last_c), dtype=bool)` | Both create a `(1, last_c)` all-`True` array |
| `rbind(new_row, pred.np)` | `np.vstack([new_row, pred_np])` | Prepend by reversing the argument order |
| `rbind(pred.np, new_row)` | `np.vstack([pred_np, new_row])` | Append in the same order |
| `pred.np[1L, ]` (1-based) | `pred_np[0, :]` (0-based) | Index shift: R's `1L` -> Python's `0` |
| `pred.np[last.r, ]` (1-based) | `pred_np[last_r - 1, :]` (0-based) | Index shift for the last row |
| `c(NA, cutoffs)` | `np.concatenate([[np.nan], cutoffs])` | `NA` for float arrays maps to `np.nan` |

---

### 4.2 Vertical Concatenation of Two Integer Matrices (ordered-factor split assembly)

**Locations:** `rpart.R` — function `rpart`, line 214.

**Original R Context**

```r
# cs:   integer matrix, shape (ncat, max_cats)  — existing categorical splits
# newc: integer matrix, shape (nadd, max_cats)  — new splits for ordered factors
# Both matrices have been aligned to the same column count beforehand (via cbind).
catmat <- rbind(cs, newc)
```

- `cs` is `rpfit$csplit`, a raw integer matrix from the C backend, possibly padded with `cbind`.
- `newc` is a freshly allocated integer matrix whose rows encode ordered-factor cut directions.
- Return type: integer matrix of shape `(ncat + nadd, max_cats)`.

**Python Equivalent**

```python
import numpy as np

# cs:   np.ndarray of dtype np.int32 (or int64), shape (ncat, max_cats)
# newc: np.ndarray of dtype np.int32 (or int64), shape (nadd, max_cats)
# Both arrays must already have the same number of columns.
catmat = np.vstack([cs, newc])
```

**Explanation**

| R | Python | Notes |
|---|---|---|
| `rbind(cs, newc)` | `np.vstack([cs, newc])` | Direct analog; both require matching column counts |
| Integer storage mode | `dtype=np.int32` or `np.int64` | Preserve integer dtype to avoid silent float promotion |
| Result shape `(ncat+nadd, max_cats)` | Same shape from `vstack` | No shape difference |

`np.concatenate([cs, newc], axis=0)` is an equally valid alternative and may be slightly more explicit in multi-axis code.

---

### 4.3 Stacking Numeric Vectors with an `NA` Sentinel for Polyline Construction

**Locations:** `rpart.branch.R` — function `rpart.branch`, lines 22–24.

**Original R Context**

```r
# x, y:     numeric vectors of node coordinates, length = number of nodes
# is.left:  logical index vector
# parent:   integer index vector (positions of parent nodes)
# sibling:  integer index vector (positions of sibling nodes)
# temp:     numeric vector (horizontal offset for branch elbow)

temp <- (x[sibling] - x[is.left]) * (1 - branch) / 2

xx <- rbind(x[is.left], x[is.left] + temp,
            x[sibling] - temp, x[sibling], NA)

yy <- rbind(y[is.left], y[parent], y[parent], y[sibling], NA)
```

- Each positional argument to `rbind` is a numeric vector of length `n_left` (number of left children), except `NA` which expands to a length-`n_left` row of `NA`.
- Results `xx` and `yy` are numeric matrices of shape `(5, n_left)`.
- They are consumed directly by `lines()` in the calling code: the `NA` row acts as a pen-lift separator between horseshoes.

**Python Equivalent**

```python
import numpy as np

# x, y:     np.ndarray of dtype float64, shape (n_nodes,)
# is_left:  boolean np.ndarray, shape (n_nodes,)
# parent:   integer np.ndarray (indices into node array)
# sibling:  integer np.ndarray (indices into node array)
# branch:   scalar float

temp = (x[sibling] - x[is_left]) * (1 - branch) / 2
n_left = is_left.sum()
nan_row = np.full((1, n_left), np.nan)

xx = np.vstack([
    x[is_left].reshape(1, -1),
    (x[is_left] + temp).reshape(1, -1),
    (x[sibling] - temp).reshape(1, -1),
    x[sibling].reshape(1, -1),
    nan_row,
])

yy = np.vstack([
    y[is_left].reshape(1, -1),
    y[parent].reshape(1, -1),
    y[parent].reshape(1, -1),
    y[sibling].reshape(1, -1),
    nan_row,
])
```

If the downstream code consuming `xx` and `yy` expects column-major (Fortran) order or a flattened sequence (as `lines()` would use), flatten with `xx.ravel(order='F')` / `yy.ravel(order='F')` to replicate R's column-major memory layout.

**Explanation**

| R | Python | Notes |
|---|---|---|
| `rbind(vec1, vec2, ..., NA)` | `np.vstack([v.reshape(1,-1), ..., nan_row])` | `vstack` requires 2-D inputs; `.reshape(1,-1)` converts a 1-D vector to a single-row 2-D array |
| Bare `NA` argument | `np.full((1, n_left), np.nan)` | R auto-expands scalar `NA` to fill a full row; Python requires explicit construction |
| Result shape `(5, n_left)` | Same from `vstack` | Identical shape |
| `x[is.left]` (logical subsetting) | `x[is_left]` (boolean indexing) | Same semantics; ensure `is_left` is a `bool` array |
| `x[parent]` (integer index) | `x[parent]` (integer array indexing) | Same semantics; R is 1-based but if `parent` was already converted to 0-based Python indices this is transparent |
| Numeric coercion from `NA` | Float promotion from `np.nan` | Both require float storage; cast integer arrays with `.astype(float)` before inserting `np.nan` |
