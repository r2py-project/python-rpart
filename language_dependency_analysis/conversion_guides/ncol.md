# Conversion Guide: `ncol` (R to Python)

---

## 1. Overview of `ncol` in R

`ncol(x)` returns the number of columns of a matrix or data frame `x` as a single integer. It is equivalent to `dim(x)[2]`. When applied to a one-dimensional vector (non-matrix), it returns `NULL`. It is a pure introspection function — it never modifies its argument and always produces a scalar integer result.

**Signature:** `ncol(x)`

- **Input:** any R object that has a `dim` attribute (matrix, data frame, array with at least 2 dimensions).
- **Output:** a length-1 integer, or `NULL` if `x` has no `dim`.

---

## 2. Contextual Usage Analysis

Across all call sites in the CSV, `ncol` is applied exclusively to 2-D objects (matrices and data frames). No call is made on a plain vector. The recurring patterns are:

| Pattern | Description |
|---|---|
| **Dimension query for array construction** | `ncol(X)` is stored in a variable (`nvar`) or used directly to size other arrays. |
| **Guard / validation check** | `ncol(p.rpart) < 5L` and `ncol(y) != 2L` are used to validate that an object has the expected number of columns before proceeding. |
| **Arithmetic in matrix expressions** | `ncol(xmiss)` feeds directly into a matrix-vector product (`%*% rep(1, ncol(xmiss))`) and a comparison, to count per-row missing values. |
| **Column arithmetic for indexing** | `(ncol(yval) - 2L)/2L` derives the number of classes from a composite matrix; `ncol(rpfit$cptable)` extracts the number of cross-validation folds stored as columns. |
| **Conditional branch on shape** | `ncol(cs)` and `ncol(newc)` are compared to decide whether column padding is needed before binding two matrices. |

In every case the argument is a 2-D NumPy array or a pandas DataFrame in the translated Python code.

---

## 3. Python Conversion Strategy

The direct Python equivalent is **`numpy.ndarray.shape[1]`** (or equivalently the `shape` attribute index 1). This is preferred over `len(x[0])` or `pandas.DataFrame.shape[1]` because:

- All numeric matrices in the rpart translation are represented as 2-D NumPy arrays.
- `array.shape[1]` is a zero-cost attribute read — no computation, no copy.
- It matches R's scalar integer semantics exactly.

For pandas DataFrames (where they occur), `df.shape[1]` is the identical idiom and is equally preferred.

**Import required:** `import numpy as np` (already present in all translated files).

---

## 4. Step-by-Step Conversion Examples

### 4.1 Dimension Query for Array Construction

**Locations:** `rpart.R / rpart` (lines 33, 83), `xpred.rpart.R / xpred.rpart` (line 49)

**Original R Context:**

```r
# rpart.R, lines 31-33 and 82-83
X <- rpart.matrix(m)     # X is a numeric matrix: nobs x nvar
nobs <- nrow(X)
nvar <- ncol(X)          # integer: number of predictor columns

# rpart.R, line 83
cats <- rep(0L, ncol(X)) # zero-vector of length nvar

# xpred.rpart.R, line 49
nvar <- ncol(X)
```

- `X` is a 2-D numeric matrix (rows = observations, columns = predictor variables).
- `ncol(X)` returns a single integer used to size subsequent vectors.

**Python Equivalent:**

```python
import numpy as np

# X is a 2-D numpy array of shape (nobs, nvar)
nobs = X.shape[0]
nvar = X.shape[1]          # equivalent to ncol(X)

cats = np.zeros(nvar, dtype=np.int32)  # equivalent to rep(0L, ncol(X))
```

**Explanation:** `X.shape` is a tuple `(nrows, ncols)`; index `[1]` gives the column count. `np.zeros(nvar, dtype=np.int32)` replicates `rep(0L, ncol(X))`.

---

### 4.2 Guard / Validation Check

**Locations:** `plotcp.R / plotcp` (line 10), `rpart.poisson.R / rpart.poisson` (line 4)

**Original R Context:**

```r
# plotcp.R, line 10
p.rpart <- x$cptable        # numeric matrix: metrics x cp_values
if (ncol(p.rpart) < 5L)
    stop("'cptable' does not contain cross-validation results")

# rpart.poisson.R, lines 3-5
if (is.matrix(y)) {
    if (ncol(y) != 2L)
        stop("response must be a 2 column matrix or a vector")
```

- `p.rpart` is a 2-D numeric matrix; the number of columns indicates whether cross-validation results are present.
- `y` is either a 2-D matrix or a 1-D vector; the check guards against incorrectly shaped response matrices.

**Python Equivalent:**

```python
# plotcp equivalent
p_rpart = x.cptable  # 2-D numpy array
if p_rpart.shape[1] < 5:
    raise ValueError("'cptable' does not contain cross-validation results")

# rpart_poisson equivalent
if isinstance(y, np.ndarray) and y.ndim == 2:
    if y.shape[1] != 2:
        raise ValueError("response must be a 2 column matrix or a vector")
```

**Explanation:** `shape[1]` replaces `ncol(...)`. The `isinstance` + `ndim` check replicates `is.matrix(y)`. Python raises `ValueError` in place of R's `stop()`.

---

### 4.3 Arithmetic in Matrix Expressions (Missing-Value Row Filter)

**Locations:** `na.rpart.R / na.rpart` (lines 7, 12, 13, 14)

**Original R Context:**

```r
# na.rpart.R, lines 6-14
xmiss <- is.na(x)            # logical matrix: same shape as x
keep <- (xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)
# ...
xmiss <- is.na(x[-yvar])
ymiss <- is.na(x[[yvar]])
keep <- if (is.matrix(ymiss))
    ((xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)) &
        ((ymiss %*% rep(1, ncol(ymiss))) == 0)
else ((xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)) & !ymiss
```

- `xmiss` and `ymiss` are boolean matrices (rows = observations, columns = variables).
- `rep(1, ncol(xmiss))` creates an all-ones column vector used to row-sum the boolean matrix via matrix multiplication.
- The result is a logical vector `keep` selecting rows that have fewer than `ncol(xmiss)` missing predictors (i.e. at least one predictor is non-missing) and zero missing response values.

**Python Equivalent:**

```python
import numpy as np

# Case 1: no response variable
xmiss = np.isnan(x)                          # bool array, shape (n, p)
keep = xmiss.sum(axis=1) < xmiss.shape[1]   # row-wise sum < ncol

# Case 2: with response variable (matrix ymiss)
xmiss = np.isnan(x_no_yvar)
ymiss = np.isnan(y_col)
if ymiss.ndim == 2:
    keep = (xmiss.sum(axis=1) < xmiss.shape[1]) & (ymiss.sum(axis=1) == 0)
else:
    keep = (xmiss.sum(axis=1) < xmiss.shape[1]) & (~ymiss)
```

**Explanation:**
- `xmiss %*% rep(1, ncol(xmiss))` is a matrix-vector product that row-sums the boolean matrix; `xmiss.sum(axis=1)` is the direct NumPy equivalent and is more readable.
- `ncol(xmiss)` becomes `xmiss.shape[1]`.
- `ncol(ymiss)` becomes `ymiss.shape[1]` (used in the `ymiss` row-sum check).
- `!ymiss` (element-wise NOT on a vector) becomes `~ymiss`.

---

### 4.4 Column Arithmetic for Class/Index Derivation

**Locations:** `rpart.class.R / rpart.class` (lines 61, 70, 75, 98), `rpart.R / rpart` (line 179)

**Original R Context:**

```r
# rpart.class.R — inside print/summary/text closures
# yval is a matrix: rows = nodes, columns = [class | class_counts... | probs... | nodeprob]
nclass <- (ncol(yval) - 2L) / 2L    # derives number of classes

# rpart.R, line 179
numcp <- ncol(rpfit$cptable)         # number of cp values (columns of cptable)
```

- `yval` is a 2-D numeric matrix where each row is a node; the number of classes is encoded in the column layout.
- `rpfit$cptable` is a 2-D matrix where each column is one cp value.

**Python Equivalent:**

```python
# rpart_class closures
# yval is a 2-D numpy array
nclass = (yval.shape[1] - 2) // 2   # integer division; ncol(yval) -> yval.shape[1]

# rpart main function
numcp = rpfit_cptable.shape[1]       # ncol(rpfit$cptable) -> shape[1]
```

**Explanation:** `ncol(yval)` maps to `yval.shape[1]`. R's integer division `/ 2L` on an integer result maps to Python's `// 2` to ensure an integer is returned.

---

### 4.5 Column Padding Before Matrix Row-Binding

**Locations:** `rpart.R / rpart` (lines 212 — both `ncol(cs)` and `ncol(newc)`)

**Original R Context:**

```r
# rpart.R, lines 211-214
cs <- rpfit$csplit          # integer matrix: existing categorical splits
ncs <- ncol(cs)
ncc <- ncol(newc)
if (ncs < ncc) cs <- cbind(cs, matrix(0L, nrow(cs), ncc - ncs))
rbind(cs, newc)
```

- `cs` and `newc` are integer matrices of potentially different column counts.
- `ncol` is used to compare widths and pad the narrower matrix with zeros before binding.

**Python Equivalent:**

```python
import numpy as np

# cs and newc are 2-D integer numpy arrays
ncs = cs.shape[1]
ncc = newc.shape[1]
if ncs < ncc:
    padding = np.zeros((cs.shape[0], ncc - ncs), dtype=np.int32)
    cs = np.hstack([cs, padding])
catmat = np.vstack([cs, newc])
```

**Explanation:**
- `ncol(cs)` -> `cs.shape[1]`, `ncol(newc)` -> `newc.shape[1]`.
- `cbind(cs, matrix(0L, nrow(cs), ncc - ncs))` -> `np.hstack([cs, padding])` where `padding` is a zero array of shape `(cs.shape[0], ncc - ncs)`.
- `rbind(cs, newc)` -> `np.vstack([cs, newc])`.

---

### 4.6 Conditional `ncol` on a Possibly-Matrix Object

**Locations:** `xpred.rpart.R / xpred.rpart` (lines 36, 40, 44, 105), `rpart.exp.R / rpart.exp` (line 17), `rpart.R / tfun` (line 152)

**Original R Context:**

```r
# xpred.rpart.R, lines 36, 40, 44
numy <- if (is.matrix(Y)) ncol(Y) else 1L

# rpart.exp.R, line 17
ny <- ncol(y)   # y is always a Surv matrix (2 or 3 columns)

# rpart.R, line 152 (inside tfun)
tfun <- function(x)
    if (is.matrix(x)) rep(is.ordered(x), ncol(x)) else is.ordered(x)
```

- `Y` may be a 2-D matrix or a 1-D vector. The pattern `if (is.matrix(Y)) ncol(Y) else 1L` safely handles both cases.
- `y` in `rpart.exp` is always a `Surv` matrix with 2 or 3 columns; `ncol(y)` extracts the column count to distinguish these cases.
- In `tfun`, `ncol(x)` is used to replicate a scalar logical across all columns of a matrix variable.

**Python Equivalent:**

```python
import numpy as np

# xpred_rpart: conditional on matrix vs vector
numy = Y.shape[1] if Y.ndim == 2 else 1

# rpart_exp: Surv matrix always 2-D
ny = y.shape[1]   # 2 or 3, used to distinguish start/stop vs stop-only Surv

# tfun equivalent: replicate ordered flag across columns
def tfun(x):
    if isinstance(x, np.ndarray) and x.ndim == 2:
        return np.full(x.shape[1], is_ordered(x), dtype=bool)
    else:
        return is_ordered(x)
```

**Explanation:**
- `is.matrix(Y)` -> `Y.ndim == 2`.
- `ncol(Y)` -> `Y.shape[1]`.
- `rep(is.ordered(x), ncol(x))` -> `np.full(x.shape[1], is_ordered(x), dtype=bool)`, which creates a boolean array of length `ncol(x)` filled with the scalar result of `is_ordered(x)`.
- The fallback `else 1L` / `else is.ordered(x)` is preserved as the scalar branch.
