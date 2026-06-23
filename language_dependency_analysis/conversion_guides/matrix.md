# Conversion Guide: `matrix` in R

## 1. Overview of `matrix` in R

`matrix()` is a base R function that creates a two-dimensional array (matrix) from a given data vector. Its signature is:

```r
matrix(data = NA, nrow = 1, ncol = 1, byrow = FALSE, dimnames = NULL)
```

Key behaviours:
- `data`: the fill value(s). A scalar is recycled to fill every cell; a vector is recycled column-by-column (or row-by-row when `byrow = TRUE`).
- `nrow` / `ncol`: dimensions. If only one is supplied R derives the other from `length(data)`.
- `byrow`: when `TRUE`, data fills the matrix row-first instead of the default column-first order.
- `dimnames`: a length-2 list `list(row_names, col_names)`.
- Return value: an R matrix object — a 2-D numeric, logical, integer, or character array depending on the type of `data`.

## 2. Contextual Usage Analysis

Across the CSV rows the calls fall into five distinct patterns:

| Pattern | Description | Files / Functions |
|---------|-------------|-------------------|
| A | Reshape an existing flat vector into a matrix (column-fill, default `byrow = FALSE`) | `formatg.R/formatg`, `rpart.R/rpart` (lines 185, 256), `rpart.class.R/rpart.class` (lines 37, 51, 85, 87, 105), `rpartcallback.R/rpartcallback` (lines 62, 73, 81) |
| B | Reshape an existing flat vector into a matrix with `byrow = TRUE` | `xpred.rpart.R/xpred.rpart` (line 141) |
| C | Fill a matrix entirely with a scalar constant (zero, `FALSE`, `TRUE`) | `roc.rpart.R/roc.rpart` (lines 18, 24, 30-37, 41), `zzz.R/descendants` (lines 38, 40) |
| D | Construct a matrix from a multi-column concatenation with named dimensions | `rpart.R/rpart` (line 185) |
| E | Construct a single-row matrix from a vector (forcing `nrow = 1`) | `rpart.class.R/rpart.class` (line 67), `rpart.poisson.R/rpart.poisson` (line 45), `zzz.R/descendants` (line 38) |

Data types involved:
- Numeric doubles (`0`, raw prediction vectors, split-statistic arrays).
- Logical booleans (`FALSE`, `TRUE` fill matrices used as boolean masks).
- Integer (`0L`, category split tables).
- Character strings (formatted numbers from `sprintf`, reshaped in `formatg`).

The dominant pattern is column-fill reshaping of an existing vector, which maps directly to NumPy's default Fortran-order (column-major) reshaping.

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

R matrices are inherently vectorised, multi-typed, 2-D arrays — exactly what `numpy.ndarray` represents. `numpy` provides:

- `numpy.reshape()` — equivalent to column-fill (requires order `'F'`) and row-fill (`order='C'`) reshaping.
- `numpy.full()` — fills a matrix with a constant scalar (equivalent to `matrix(scalar, nrow, ncol)`).
- `numpy.zeros()` / `numpy.ones()` / `numpy.full(…, False)` / `numpy.full(…, True)` — typed constant-fill variants.

`pandas` is not used here because none of these calls attach persistent index metadata; they are transient arrays manipulated by downstream arithmetic and indexing. `numpy` arrays are also directly compatible with the rest of the rpart Python port which uses NumPy for all numerical work.

## 4. Step-by-Step Conversion Examples

---

### Pattern A — Reshape a flat vector into a matrix (column-fill, `byrow = FALSE`)

**Locations:**
- `formatg.R` / `formatg` (line 9)
- `rpart.R` / `rpart` (lines 256, 193, 213)
- `rpart.class.R` / `rpart.class` (lines 37, 51, 85, 87, 105)
- `rpartcallback.R` / `rpartcallback` (lines 62, 73, 81)

**Original R Context:**

`data` is either a pre-existing vector or the result of a C-to-R pointer unpack. `nrow` or `ncol` (but not both) is specified, and R infers the missing dimension. Fill order is column-major (R's default).

```r
# Generic form — ncol supplied, nrow inferred
result <- matrix(vec, ncol = k)

# Generic form — nrow supplied, ncol inferred
result <- matrix(vec, nrow = m)

# Concrete examples from the source
matrix(temp, nrow = nrow(x))                              # formatg.R:9
matrix(rpfit$dnode[, 4L + (0L:numclass)], ncol = numclass + 1L)  # rpart.R:256
matrix(yback[1L:(nback * numy)], ncol = numy)             # rpartcallback.R:62
matrix(temp2, ncol = numclass)                            # rpart.class.R:37
```

**Python Equivalent:**

```python
import numpy as np

# Generic form — ncol supplied, nrow inferred
result = vec.reshape(-1, k, order='F')

# Generic form — nrow supplied, ncol inferred
result = vec.reshape(m, -1, order='F')

# Concrete equivalents
result = temp.reshape(-1, x.shape[0], order='F').T      # when nrow=nrow(x) is given
result = rpfit_dnode_cols.reshape(-1, numclass + 1, order='F')
result = yback[:nback * numy].reshape(-1, numy, order='F')
result = temp2.reshape(-1, numclass, order='F')
```

**Explanation:**

R fills matrices column by column (Fortran / column-major order). NumPy's default `reshape` is C-order (row-major). Passing `order='F'` to `numpy.reshape` replicates R's column-fill behaviour exactly. `-1` lets NumPy infer the complementary dimension, mirroring R's automatic dimension derivation. When `nrow` is given instead of `ncol`, the shape tuple is `(m, -1)` with `order='F'`; when `ncol` is given it is `(-1, k)` with `order='F'`.

---

### Pattern B — Reshape a flat vector into a matrix with row-fill (`byrow = TRUE`)

**Locations:**
- `xpred.rpart.R` / `xpred.rpart` (line 141)

**Original R Context:**

`pred` is a flat double vector returned by `.Call(C_xpred, ...)`. It is reshaped into `nrow(X)` rows, filling row by row, and given row/column names.

```r
# pred: numeric vector, length = nrow(X) * length(cp)
matrix(pred, nrow = nrow(X), byrow = TRUE,
       dimnames = list(rownames(X), format(cp)))
```

Return type: numeric matrix of shape `(nrow(X), length(cp))`.

**Python Equivalent:**

```python
import numpy as np

# pred: 1-D numpy array, length = n_rows * n_cp
# row_names: list of row label strings
# col_names: list of formatted cp strings
result = pred.reshape(n_rows, -1)          # default C-order = row-fill = byrow=TRUE

# To attach labels, wrap in a pandas DataFrame
import pandas as pd
result_df = pd.DataFrame(
    pred.reshape(n_rows, -1),
    index=row_names,
    columns=col_names
)
```

**Explanation:**

`byrow = TRUE` in R corresponds to NumPy's default `order='C'` (row-major), so a plain `reshape(n_rows, -1)` is correct here — no `order='F'` needed. The `dimnames` argument attaches row and column labels; in Python these are expressed as a `pandas.DataFrame` index and columns, or simply stored separately as lists when the downstream code accesses them by position.

---

### Pattern C — Fill a matrix entirely with a constant scalar

**Locations:**
- `roc.rpart.R` / `roc.rpart` (lines 18, 24, 30–37, 41)
- `zzz.R` / `descendants` (lines 38, 40)

**Original R Context:**

These calls create brand-new matrices pre-filled with a single value: `0`, `FALSE`, or `TRUE`. No data vector is recycled — R simply repeats the scalar.

```r
# Logical fill
matrix(FALSE, nrow = 1L, ncol = last.c)       # roc.rpart.R:18
matrix(TRUE,  nrow = 1L, ncol = last.c)       # roc.rpart.R:24
matrix(TRUE,  1L, 1L)                          # zzz.R:38
matrix(FALSE, n, n)                            # zzz.R:40

# Numeric zero fill
matrix(0, nrow = cutoff.n, ncol = 1L)         # roc.rpart.R:30-37
matrix(0, nrow = 2L, ncol = 2L)               # roc.rpart.R:41
```

Return types: logical matrix (`FALSE`/`TRUE` fill) or numeric matrix (`0` fill).

**Python Equivalent:**

```python
import numpy as np

# Logical fill — FALSE
matrix_false_row = np.full((1, last_c), False, dtype=bool)   # 1 x last_c
matrix_false_sq  = np.full((n, n), False, dtype=bool)        # n x n

# Logical fill — TRUE
matrix_true_row  = np.full((1, last_c), True,  dtype=bool)   # 1 x last_c
matrix_true_one  = np.full((1, 1),      True,  dtype=bool)   # 1 x 1

# Numeric zero fill
col_vec  = np.zeros((cutoff_n, 1), dtype=float)  # cutoff_n x 1
sq_2x2   = np.zeros((2, 2),        dtype=float)  # 2 x 2
```

**Explanation:**

`numpy.zeros()` is the most idiomatic equivalent for `matrix(0, m, n)`. For logical constants `numpy.full(..., False/True, dtype=bool)` is preferred over `numpy.zeros(..., dtype=bool)` because it makes the fill intent explicit and mirrors R's type-preserving scalar recycling. The dimension argument `(nrow, ncol)` maps directly to NumPy's `shape` tuple `(m, n)`. Note that `ncol = 1L` in R produces a true column-vector matrix; in NumPy use shape `(m, 1)` (2-D) rather than a 1-D array if downstream code indexes with two indices.

---

### Pattern D — Construct a matrix from concatenated columns with named dimensions

**Locations:**
- `rpart.R` / `rpart` (line 185)

**Original R Context:**

Several integer and double sub-matrices from the C fit object are concatenated with `c()` (which flattens to a single vector column-by-column) and then reshaped with `ncol = 5L`. Named rows and columns are attached via `dimnames`.

```r
# rpfit$isplit[, 2:3]: integer matrix, ncol = 2
# rpfit$dsplit:        double matrix, ncol = 3
# c(...) concatenates all columns → flat vector of length nsplit * 5
splits <- matrix(
    c(rpfit$isplit[, 2:3], rpfit$dsplit),
    ncol = 5L,
    dimnames = list(
        tname[rpfit$isplit[, 1L] + 1L],
        c("count", "ncat", "improve", "index", "adj")
    )
)
```

Return type: numeric matrix, shape `(nsplit, 5)`, with row and column names.

**Python Equivalent:**

```python
import numpy as np

# Equivalent: column-stack then name with a DataFrame
isplit_cols = rpfit_isplit[:, 1:3]    # columns 2:3 (0-based: indices 1 and 2)
dsplit      = rpfit_dsplit             # all columns of dsplit

# R's c() on column matrices flattens column-by-column → order='F' concatenation
flat = np.concatenate([isplit_cols.ravel(order='F'), dsplit.ravel(order='F')])
splits = flat.reshape(-1, 5, order='F')

# Attach names via pandas for downstream label-based access
import pandas as pd
row_names = [tname[i] for i in rpfit_isplit[:, 0]]   # isplit[:,1] in R = index 0 in Python
splits_df = pd.DataFrame(
    splits,
    index=row_names,
    columns=["count", "ncat", "improve", "index", "adj"]
)
```

**Explanation:**

R's `c()` applied to matrices flattens them column-by-column. In Python the equivalent is `.ravel(order='F')` on each sub-array followed by `np.concatenate`. The combined flat vector is then reshaped column-fill with `order='F'` and `ncol=5`. R column indexing `[, 2:3]` is 1-based and inclusive, corresponding to Python `[:, 1:3]` (0-based, exclusive end). `dimnames` is reproduced as a `pandas.DataFrame` with `index` and `columns`.

---

### Pattern E — Force a vector into a single-row matrix (`nrow = 1`)

**Locations:**
- `rpart.class.R` / `rpart.class` (line 67)
- `rpart.poisson.R` / `rpart.poisson` (line 45)
- `zzz.R` / `descendants` (line 38, covered under Pattern C for the `TRUE` fill case)

**Original R Context:**

A plain vector (result of `formatg()`, or `yval`) is coerced into a 1-row matrix so that downstream code treating it as a matrix (e.g. indexing with two subscripts `[row, col]`) does not fail.

```r
# rpart.class.R:67 — yprob is a character vector when nclass < 5
if (!is.matrix(yprob))
    yprob <- matrix(yprob, nrow = 1L)

# rpart.poisson.R:45
if (!is.matrix(yval))
    yval <- matrix(yval, nrow = 1L)
```

Return type: a 1-row matrix of the same element type as the input vector.

**Python Equivalent:**

```python
import numpy as np

# Equivalent guard: ensure array is 2-D with shape (1, n)
if yprob.ndim == 1:
    yprob = yprob.reshape(1, -1)

if yval.ndim == 1:
    yval = yval.reshape(1, -1)
```

**Explanation:**

R's `matrix(vec, nrow = 1L)` is equivalent to giving the vector a shape of `(1, len(vec))`. In NumPy the idiomatic check is `.ndim == 1` followed by `.reshape(1, -1)`. The `-1` lets NumPy infer the column count. No `order` argument is needed because a 1-D array has no ambiguity about fill order — the single row is the array itself.
