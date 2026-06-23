# Conversion Guide: `exp` (R to Python)

---

## 1. Overview of `exp` in R

`exp(x)` computes the natural exponential function e^x for each element of `x`. It is a base R function defined in the `base` package and requires no imports.

Key characteristics:

- **Input:** A numeric scalar, vector, matrix, or array. When `x` is a vector or matrix, the function operates element-wise across all elements.
- **Output:** A numeric object of the same shape and type as the input, where every element `x[i]` is replaced by `e^x[i]`.
- **Vectorization:** Like all base R arithmetic functions, `exp` is fully vectorized. Passing a length-n vector returns a length-n vector with no explicit looping required.
- **Special values:** `exp(0)` returns `1`, `exp(Inf)` returns `Inf`, `exp(-Inf)` returns `0`, and `exp(NA)` returns `NA`.

---

## 2. Contextual Usage Analysis

All three usages in the CSV apply `exp` to a variable named `offset`, which in both `rpart.exp` and `rpart.poisson` is a numeric vector of length `n` (one offset value per observation). The surrounding code confirms the vector nature of `offset`:

- In `rpart.exp.R` (line 107), `offset` is guarded by `length(offset) == n`, where `n = nrow(y)`, explicitly confirming it is a length-n numeric vector. The result `exp(offset)` is used in element-wise multiplication with `newy`, another length-n numeric vector.
- In `rpart.poisson.R` (line 6), `exp(offset)` scales the first column of a two-column numeric matrix `y` via element-wise multiplication (`y[, 1L] * exp(offset)`).
- In `rpart.poisson.R` (line 9), `exp(offset)` is passed as the first argument to `cbind`, constructing it as the first column of a new matrix. Here `offset` is a numeric vector, so `exp(offset)` is also a numeric vector that becomes a matrix column.

Recurring pattern: In every case, `exp` is applied to a numeric vector and the result is used in a vectorized arithmetic context (element-wise multiplication or matrix column construction). There are no scalar-only usages.

---

## 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy.exp`).

Rationale:

- R's `exp` is inherently vectorized. `numpy.exp` is the direct NumPy equivalent and operates element-wise on arrays of any shape, matching R's behavior exactly.
- In the rpart Python port, `offset` will be represented as a 1-D `numpy.ndarray` (shape `(n,)`), mirroring R's numeric vector. `numpy.exp` handles this natively.
- The standard library `math.exp` only accepts scalars and would require an explicit loop over `offset`, making it incorrect and inefficient for the vector contexts present here.
- `numpy.exp` also replicates R's handling of special values (`np.inf`, `-np.inf`, `np.nan`) without any additional configuration.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Applying `exp(offset)` as an element-wise scale factor on a vector

**Locations:**
- File: `rpart/R/rpart.exp.R`, Function: `rpart.exp`, Line 107

**Original R Context:**

```r
# offset: numeric vector of length n (one value per observation)
# newy:   numeric vector of length n (rescaled time axis values)
if (length(offset) == n)  newy <- newy * exp(offset)
```

`offset` is a numeric vector confirmed to have exactly `n` elements. `exp(offset)` produces a numeric vector of the same length, and the multiplication with `newy` is performed element-wise.

**Python Equivalent:**

```python
import numpy as np

# offset: np.ndarray of shape (n,), dtype float64
# newy:   np.ndarray of shape (n,), dtype float64
if offset is not None and len(offset) == n:
    newy = newy * np.exp(offset)
```

**Explanation:**

- `np.exp(offset)` applies `e^x` element-wise to every entry of the 1-D array `offset`, returning a new array of the same shape and dtype — directly equivalent to R's `exp(offset)` on a numeric vector.
- The Python guard `offset is not None` replaces R's `length(offset) == n` length check. In the Python port, the absence of an offset is represented by `None` rather than a zero-length vector, so both conditions should be checked: `offset is not None and len(offset) == n`.
- The `*` operator between two NumPy arrays performs element-wise multiplication, identical to R's `*` on two vectors of equal length.
- No looping is required; NumPy broadcasts and computes the result in a single vectorized call.

---

### 4.2 Applying `exp(offset)` to scale a matrix column in-place

**Locations:**
- File: `rpart/R/rpart.poisson.R`, Function: `rpart.poisson`, Line 6

**Original R Context:**

```r
# y:      numeric matrix with at least 2 columns, nrow == n
# offset: numeric vector of length n
if (is.matrix(y)) {
    if (ncol(y) != 2L)
        stop("response must be a 2 column matrix or a vector")
    if (!is.null(offset)) y[, 1L] <- y[, 1L] * exp(offset)
}
```

When `y` is a two-column matrix, the first column (exposure/time) is scaled by `exp(offset)` in-place. R uses 1-based column indexing (`y[, 1L]`).

**Python Equivalent:**

```python
import numpy as np

# y:      np.ndarray of shape (n, 2), dtype float64
# offset: np.ndarray of shape (n,), dtype float64, or None
if isinstance(y, np.ndarray) and y.ndim == 2:
    if y.shape[1] != 2:
        raise ValueError("response must be a 2 column matrix or a vector")
    if offset is not None:
        y[:, 0] = y[:, 0] * np.exp(offset)
```

**Explanation:**

- R's `y[, 1L]` (1-based first column) becomes `y[:, 0]` in Python (0-based first column).
- `np.exp(offset)` produces a 1-D array of shape `(n,)`, which NumPy broadcasts correctly against `y[:, 0]` (also shape `(n,)`) in the element-wise multiplication.
- R's `!is.null(offset)` translates to `offset is not None` in Python.
- The in-place assignment `y[:, 0] = ...` modifies the column directly, matching R's `y[, 1L] <- ...` semantics. Note that if `y` is a NumPy array slice rather than a contiguous array, care should be taken to ensure the assignment propagates as intended.

---

### 4.3 Applying `exp(offset)` to construct a matrix column with `cbind`

**Locations:**
- File: `rpart/R/rpart.poisson.R`, Function: `rpart.poisson`, Line 9

**Original R Context:**

```r
# y:      numeric vector of length n (event counts)
# offset: numeric vector of length n
if (is.null(offset)) y <- cbind(1, y)
else                  y <- cbind(exp(offset), y)
```

When `y` is a plain vector (not already a matrix), it is combined with either a column of ones or a column of `exp(offset)` to form a two-column matrix. The first column becomes the exposure/time, and the second column holds the event counts.

**Python Equivalent:**

```python
import numpy as np

# y:      np.ndarray of shape (n,), dtype float64 (event counts)
# offset: np.ndarray of shape (n,), dtype float64, or None
if y.ndim == 1:
    if offset is None:
        y = np.column_stack([np.ones(len(y)), y])
    else:
        y = np.column_stack([np.exp(offset), y])
```

**Explanation:**

- R's `cbind(exp(offset), y)` binds two vectors as columns of a matrix. The Python equivalent is `np.column_stack([np.exp(offset), y])`, which stacks 1-D arrays as columns into a 2-D array of shape `(n, 2)`.
- `np.exp(offset)` computes `e^offset` element-wise for the length-n offset vector, producing the first column.
- R's `cbind(1, y)` with a scalar `1` broadcasts `1` to fill an entire column; `np.ones(len(y))` achieves the same result explicitly in NumPy.
- After this operation, `y` becomes a 2-D array of shape `(n, 2)`, where `y[:, 0]` holds the exposure values and `y[:, 1]` holds the event counts — mirroring R's resulting matrix structure.
