# Conversion Guide: `as.matrix` (R to Python)

### 1. Overview of `as.matrix` in R

`as.matrix` is a base R generic function that converts an R object into a matrix. Its primary signature is:

```r
as.matrix(x, ...)
```

**Typical inputs:** Any R object — most commonly a `data.frame`, a numeric vector, or an existing matrix-like structure.

**Expected outputs:** A two-dimensional `matrix` object with a uniform element type. When the input is a `data.frame`, coercion follows a strict type hierarchy:

- If all columns are logical, the result is a logical matrix.
- If columns are a mix of logical and integer, the result is an integer matrix.
- The hierarchy proceeds: `logical < integer < double < complex`.
- If any column is character (or a factor, which is converted via `as.vector()`), all columns are coerced to character, yielding a character matrix.

The function also preserves row names and column names from the source object as `dimnames` on the resulting matrix.

---

### 2. Contextual Usage Analysis

There is one occurrence of `as.matrix` in the provided CSV, located in `rpart/R/rpart.matrix.R` at line 12, inside the function `rpart.matrix`.

The full function reads a `frame` argument (a model frame, i.e., a `data.frame` with a `"terms"` attribute). The call to `as.matrix` appears on an early-exit guard path:

```r
if (!inherits(frame, "data.frame") ||
   is.null(attr(frame, "terms")))  return(as.matrix(frame))
```

This means `as.matrix(frame)` is reached only when one of two fallback conditions is true:

1. `frame` is **not** a `data.frame` at all (e.g., it is already a plain matrix or a numeric vector passed directly), or
2. `frame` **is** a `data.frame` but lacks the `"terms"` attribute (i.e., it was not produced by `model.frame` and therefore cannot be processed by `model.matrix`).

In both cases the function simply converts whatever it received into a matrix and returns immediately, bypassing all the column-type coercion and `model.matrix` logic that follows. The result is a numeric (or mixed-type) matrix whose dimensions and names mirror the input.

The predominant real-world inputs to `rpart.matrix` come from rpart's internals where `frame` is a model frame, so this branch acts as a defensive fallback for callers who pass a bare matrix, a data frame without terms, or a numeric object directly. The return type is always a `matrix`.

---

### 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy`), with **pandas** as a secondary tool when the input arrives as a `DataFrame`.

**Rationale:**

- R's `as.matrix` on a `data.frame` produces a 2-D array with homogeneous dtype — the direct structural equivalent in Python is a `numpy.ndarray` with `ndim == 2`.
- NumPy's `numpy.array(..., ndmin=2)` or `pandas.DataFrame.to_numpy()` replicate the coercion semantics faithfully: mixed numeric columns are promoted to a common dtype (e.g., `float64`), and mixed numeric/string columns are cast to `object` (analogous to R's character matrix).
- Because `rpart.matrix` is a preprocessing step that feeds a numeric design matrix into the tree-building algorithm, the output will in practice always be a 2-D float array. `numpy.ndarray` with `dtype=float64` is therefore the most precise and efficient equivalent.
- `pandas.DataFrame.to_numpy()` is preferred over `numpy.array(df)` when the input is a pandas `DataFrame`, because it cleanly handles column dtypes, index stripping, and mixed-type coercion in one call. For non-DataFrame inputs (plain arrays, lists), `numpy.atleast_2d(numpy.array(x))` is the direct equivalent.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Fallback conversion of a non-`data.frame` or terms-less input

**Locations:**
- File: `rpart/R/rpart.matrix.R`
- Function: `rpart.matrix`

**Original R Context:**

`frame` is one of:
- A plain numeric matrix (`matrix`, `numeric`)
- A `data.frame` that lacks a `"terms"` attribute

Return type: `matrix` (2-D, with `dimnames` inherited from the input).

```r
# Generalized R snippet
rpart.matrix <- function(frame) {
    if (!inherits(frame, "data.frame") ||
       is.null(attr(frame, "terms")))  return(as.matrix(frame))
    # ... rest of function not reached in this branch
}

# Example call paths that hit as.matrix:
# 1. frame is already a numeric matrix
m <- matrix(1:12, nrow = 3, ncol = 4)
as.matrix(m)          # returns m unchanged (already a matrix)

# 2. frame is a bare data.frame with no terms attribute
df <- data.frame(x = c(1.0, 2.0), y = c(3.0, 4.0))
as.matrix(df)         # returns a 2x2 numeric matrix
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

def as_matrix(frame):
    """
    Python equivalent of R's as.matrix() for the rpart.matrix fallback branch.

    Accepts a numpy ndarray, a pandas DataFrame, or any array-like object
    and returns a 2-D numpy ndarray, mirroring R's matrix coercion semantics.
    """
    if isinstance(frame, pd.DataFrame):
        # pandas DataFrame -> numpy 2-D array
        # to_numpy() applies dtype promotion across columns just as R does:
        #   all-numeric -> float64, mixed with str -> object (like R's char matrix)
        return frame.to_numpy()
    else:
        # Already a numpy array, a list-of-lists, or any other array-like:
        # atleast_2d ensures a 1-D vector becomes a single-row matrix,
        # matching R's behaviour for vectors.
        return np.atleast_2d(np.array(frame))


# --- Example 1: input is already a 2-D numpy array (mirrors R matrix input) ---
m = np.arange(1, 13, dtype=float).reshape(3, 4)
result = as_matrix(m)
print(result)
# [[ 1.  2.  3.  4.]
#  [ 5.  6.  7.  8.]
#  [ 9. 10. 11. 12.]]

# --- Example 2: input is a pandas DataFrame without a 'terms' equivalent ---
df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
result = as_matrix(df)
print(result)
# [[1. 3.]
#  [2. 4.]]
print(type(result))   # <class 'numpy.ndarray'>
print(result.ndim)    # 2
```

**Explanation:**

| R concept | Python equivalent | Notes |
|---|---|---|
| `as.matrix(frame)` on a `data.frame` | `df.to_numpy()` | `to_numpy()` performs the same column-wise dtype promotion R does. |
| `as.matrix(frame)` on a plain matrix | `np.atleast_2d(np.array(frame))` | `atleast_2d` ensures a 1-D array becomes a row vector `(1, n)`, matching R's behaviour where a named vector becomes a 1-row matrix. |
| R's type hierarchy (`logical < integer < double`) | NumPy's implicit upcasting | When a `DataFrame` mixes `bool` and `int` columns, `to_numpy()` promotes to `int64`; mixing numeric with `object` columns produces `object` dtype, analogous to R's character matrix. |
| `dimnames` (row/column names preserved) | Dropped by default | `to_numpy()` discards the index and column labels. If downstream code needs them, pass `df.index.tolist()` and `df.columns.tolist()` separately, or retain the `DataFrame` until labels are no longer needed. |
| Zero-based indexing | Not applicable here | `as.matrix` is a pure coercion call; no indexing arithmetic is involved in this branch. |

The key import is `import numpy as np`; `import pandas as pd` is only needed when the input arrives as a `DataFrame`. For the rpart translation context, where `frame` will typically be a pandas `DataFrame` constructed from the training data, `df.to_numpy()` is the single idiomatic replacement.
