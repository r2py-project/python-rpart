# Conversion Guide: `is.matrix` (R to Python)

---

### 1. Overview of `is.matrix` in R

`is.matrix(x)` is a base R predicate function that returns `TRUE` if the object `x` is a two-dimensional matrix, and `FALSE` otherwise. In R, a matrix is an atomic vector with a `dim` attribute of length 2. An object is considered a matrix when:

- It carries a `dim` attribute with exactly two elements (rows and columns).
- It is not a higher-dimensional array (which would have `length(dim(x)) > 2`).

**Typical inputs:** Any R object — numeric vectors, data frames, lists, character vectors, logical vectors, or objects returned from model-fitting functions.

**Return value:** A single logical scalar (`TRUE` or `FALSE`). It never returns a vector, regardless of the type of input.

**Key behavior notes:**
- A plain vector (even with multiple elements) returns `FALSE`.
- A data frame returns `FALSE`, even though it is two-dimensional.
- A one-row or one-column matrix still returns `TRUE`.
- The result controls branching logic throughout the rpart codebase: whether to call `ncol()`, how many response columns exist, and how to serialize data before passing it to C.

---

### 2. Contextual Usage Analysis

Across all 14 call sites in the CSV, `is.matrix` is used exclusively as a **type-dispatch guard** that selects between two code paths: one for matrix (multi-column) inputs and one for scalar/vector (single-column) inputs. Three distinct behavioral patterns appear:

**Pattern A — Preserve matrix shape of output (formatting/reshaping).**
Found in `formatg.R` and `rpart.class.R`. After a vectorized operation produces a flat result, `is.matrix` on the *input* determines whether the output should be reshaped back into a matrix via `matrix(...)` / forced to have `nrow = 1`.

**Pattern B — Determine number of response columns (`numy`) at runtime.**
Found in `xpred.rpart.R` (lines 36, 40, 44, 105, 114) and `rpart.R` (line 38). `is.matrix(Y)` controls whether `numy` is set to `ncol(Y)` (multi-column response) or `1L` (univariate response). This integer is later passed to C.

**Pattern C — Validate input shape or select processing branch.**
Found in `rpart.poisson.R` (line 3), `na.rpart.R` (line 11), `snip.rpart.R` (line 58), and `snip.rpart.mouse.R` (line 36). Here `is.matrix` guards against incorrect column counts, selects the right row-filtering arithmetic, or decides how to format output strings.

The objects tested are:
- `Y` / `y`: model response matrices (numeric, 1- or 2-column), returned from `model.response()` or `init$y`.
- `x`: a numeric matrix passed to `formatg`, or an rpart model object (field access via `x$csplit`, `x$splits`).
- `ymiss`: a logical NA-indicator, result of `is.na()` on a response variable.
- `yprob`, `yval`, `yval2`: numeric matrices holding per-node predicted probabilities or values.
- `ff$yval2`: a slot in the rpart frame data frame, either a matrix or a vector depending on the fitting method.

---

### 3. Python Conversion Strategy

The primary Python equivalent is **`isinstance(x, np.ndarray) and x.ndim == 2`** using `numpy`. This is the most faithful translation because:

- NumPy's `ndarray` with `ndim == 2` is the direct structural equivalent of an R matrix (a contiguous block of data with a two-element shape tuple).
- `pandas.DataFrame` is *not* equivalent: R's `is.matrix` returns `FALSE` for data frames, and the converted code should likewise distinguish DataFrames from 2-D arrays.
- `math` or other scalar libraries are irrelevant; all rpart objects in these contexts are array-like.
- In some contexts the input may be a 1-D array (equivalent to an R vector) or a 2-D array (equivalent to an R matrix), and the check selects the branch accordingly.

For pandas `Series` objects (which may arise from DataFrame column extraction), `ndim == 1` so they correctly fall through to the vector branch.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Pattern A — Reshape flat output back to matrix when input was a matrix

**Locations:** `formatg.R :: formatg` (line 9), `rpart.class.R :: rpart.class` (line 66)

**Original R Context:**

- Input `x`: a numeric matrix (`matrix`, with `dim` attribute) or a numeric vector.
- Return: a character matrix of the same shape as `x` if `x` is a matrix; otherwise a flat character vector.

```r
# formatg.R, line 9
# x is numeric (vector or matrix); temp is a character vector from sprintf
if (is.matrix(x)) matrix(temp, nrow = nrow(x)) else temp

# rpart.class.R, line 66
# yprob is a character matrix/vector produced by format()
if (!is.matrix(yprob))
    yprob <- matrix(yprob, nrow = 1L)
```

**Python Equivalent:**

```python
import numpy as np

# --- formatg equivalent ---
def formatg(x: np.ndarray, fmt: str = "{:.6g}") -> np.ndarray:
    """
    x: 1-D or 2-D numeric numpy array.
    Returns a string array of the same shape.
    """
    vectorized_format = np.vectorize(lambda v: fmt.format(v))
    temp = vectorized_format(x)
    # Preserve 2-D shape when input was a matrix
    if isinstance(x, np.ndarray) and x.ndim == 2:
        return temp.reshape(x.shape)
    return temp

# --- rpart.class print equivalent ---
# yprob: 1-D or 2-D string array produced by formatting
if not (isinstance(yprob, np.ndarray) and yprob.ndim == 2):
    yprob = yprob.reshape(1, -1)  # force to (1, n_classes)
```

**Explanation:** `sprintf(format, x)` on a matrix in R returns a flat character vector, so `matrix(temp, nrow=nrow(x))` restores the two-dimensional shape. In Python, `np.vectorize` similarly returns a flat or identically-shaped array, and `.reshape(x.shape)` / `.reshape(1, -1)` reproduces the same behavior. The guard `isinstance(x, np.ndarray) and x.ndim == 2` replaces `is.matrix(x)`.

---

#### 4.2 Pattern B — Determine `numy` (number of response columns) for passing to C

**Locations:** `rpart.R :: rpart` (line 38), `xpred.rpart.R :: xpred.rpart` (lines 36, 40, 44, 105, 114)

**Original R Context:**

- Input `Y`: a numeric matrix (two-column Poisson response, or multi-column survival/class response) or a numeric vector (univariate response).
- Return: an integer scalar `numy` consumed by `.Call(C_xpred, ..., as.integer(numy), ...)`.
- At line 38 in `rpart.R`: `is.matrix(Y)` is used to infer the fitting method (`"poisson"`) when the user does not specify one.

```r
# rpart.R, line 35-39
if (missing(method)) {
    method <- if (is.factor(Y) || is.character(Y)) "class"
              else if (inherits(Y, "Surv")) "exp"
              else if (is.matrix(Y)) "poisson"
              else "anova"
}

# xpred.rpart.R, lines 36, 40, 44, 105, 114
numy <- if (is.matrix(Y)) ncol(Y) else 1L
```

**Python Equivalent:**

```python
import numpy as np

# --- method inference (rpart.R line 35-39 equivalent) ---
import pandas as pd

def infer_method(Y) -> str:
    if isinstance(Y, pd.Categorical) or Y.dtype == object:
        return "class"
    # "Surv" objects would be represented as a specially tagged array or class
    elif isinstance(Y, SurvivalArray):   # project-specific type
        return "exp"
    elif isinstance(Y, np.ndarray) and Y.ndim == 2:
        return "poisson"
    else:
        return "anova"

# --- numy determination (xpred.rpart.R equivalent) ---
numy: int = Y.shape[1] if (isinstance(Y, np.ndarray) and Y.ndim == 2) else 1
```

**Explanation:** `ncol(Y)` in R returns the number of columns of a matrix; in Python this is `Y.shape[1]`. The fallback `1L` (R integer) maps to Python `int` `1`. The condition `is.matrix(Y)` maps to `isinstance(Y, np.ndarray) and Y.ndim == 2`. The method-inference chain translates factor/character checks to dtype checks and `inherits(Y, "Surv")` to an `isinstance` check against the project's survival array type.

---

#### 4.3 Pattern B (serialization) — Flatten matrix to double vector before C call

**Locations:** `xpred.rpart.R :: xpred.rpart` (line 114)

**Original R Context:**

- Input `Y`: a numeric matrix or numeric vector.
- Before passing to `.Call`, the matrix must be transposed and flattened (column-major to row-major) via `as.double(t(Y))`.

```r
# xpred.rpart.R, line 114
if (is.matrix(Y)) Y <- as.double(t(Y)) else storage.mode(Y) <- "double"
```

**Python Equivalent:**

```python
import numpy as np
import ctypes

if isinstance(Y, np.ndarray) and Y.ndim == 2:
    # Transpose then flatten to match R's as.double(t(Y))
    Y_flat = Y.T.ravel().astype(np.float64)
else:
    Y_flat = np.asarray(Y, dtype=np.float64).ravel()
```

**Explanation:** R stores matrices in column-major (Fortran) order. `as.double(t(Y))` transposes to row-major then flattens, which is equivalent to `Y.T.ravel()` in NumPy (which is C-order / row-major by default). For the vector case, `storage.mode(Y) <- "double"` is a no-copy type coercion, equivalent to `np.asarray(Y, dtype=np.float64)`.

---

#### 4.4 Pattern C — Validate response shape (rpart.poisson)

**Locations:** `rpart.poisson.R :: rpart.poisson` (lines 3, 45)

**Original R Context:**

- Input `y` (line 3): the raw response from the model frame; expected to be either a 2-column numeric matrix `[time, events]` or a plain numeric vector of event counts.
- Input `yval` (line 45): per-node predicted values; expected to be a matrix, forced to `matrix(..., nrow=1L)` if it is not.

```r
# rpart.poisson.R, lines 3-10
if (is.matrix(y)) {
    if (ncol(y) != 2L)
        stop("response must be a 2 column matrix or a vector")
    if (!is.null(offset)) y[, 1L] <- y[, 1L] * exp(offset)
} else {
    if (is.null(offset)) y <- cbind(1, y)
    else                 y <- cbind(exp(offset), y)
}

# rpart.poisson.R, line 45
if (!is.matrix(yval)) yval <- matrix(yval, nrow = 1L)
```

**Python Equivalent:**

```python
import numpy as np

# --- lines 3-10 equivalent ---
def prepare_poisson_response(y: np.ndarray, offset=None) -> np.ndarray:
    if isinstance(y, np.ndarray) and y.ndim == 2:
        if y.shape[1] != 2:
            raise ValueError("response must be a 2 column matrix or a vector")
        if offset is not None:
            y = y.copy()
            y[:, 0] = y[:, 0] * np.exp(offset)
    else:
        y = np.asarray(y, dtype=np.float64).ravel()
        if offset is None:
            y = np.column_stack([np.ones(len(y)), y])
        else:
            y = np.column_stack([np.exp(offset), y])
    return y

# --- line 45 equivalent ---
if not (isinstance(yval, np.ndarray) and yval.ndim == 2):
    yval = np.atleast_2d(yval)   # shape (1, n) for a 1-D array
```

**Explanation:** `cbind(1, y)` prepends a column of ones, equivalent to `np.column_stack([np.ones(len(y)), y])`. `ncol(y) != 2L` maps to `y.shape[1] != 2`. `matrix(yval, nrow=1L)` converts a vector to a 1-row matrix; `np.atleast_2d` does the same for a 1-D NumPy array (it inserts the new axis at position 0, yielding shape `(1, n)`).

---

#### 4.5 Pattern C — Guard matrix row/column operations on NA-indicator

**Locations:** `na.rpart.R :: na.rpart` (line 11)

**Original R Context:**

- Input `ymiss`: the result of `is.na(x[[yvar]])`, which returns a logical vector for a univariate response or a logical matrix for a multi-column response (e.g., survival objects with two columns).
- The branch computes the row sum differently for the two cases: matrix arithmetic `ymiss %*% rep(1, ncol(ymiss)) == 0` vs. scalar negation `!ymiss`.

```r
# na.rpart.R, lines 11-14
keep <- if (is.matrix(ymiss))
    ((xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)) &
        ((ymiss %*% rep(1, ncol(ymiss))) == 0)
else
    ((xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)) & !ymiss
```

**Python Equivalent:**

```python
import numpy as np

# xmiss: 2-D boolean array, shape (n_obs, n_predictors)
# ymiss: 1-D or 2-D boolean array

x_any_missing = xmiss.sum(axis=1) < xmiss.shape[1]   # at least one predictor present

if isinstance(ymiss, np.ndarray) and ymiss.ndim == 2:
    y_all_present = ymiss.sum(axis=1) == 0
    keep = x_any_missing & y_all_present
else:
    keep = x_any_missing & (~ymiss)
```

**Explanation:** R's matrix-vector multiply `ymiss %*% rep(1, ncol(ymiss))` is equivalent to row-wise summation, i.e., `ymiss.sum(axis=1)` in NumPy. The condition `== 0` means no missing values in the response row. For the vector branch, `!ymiss` is `~ymiss` in NumPy.

---

#### 4.6 Pattern C — Conditional field access on rpart object slots

**Locations:** `snip.rpart.R :: snip.rpart` (line 58), `snip.rpart.mouse.R :: snip.rpart.mouse` (line 36)

**Original R Context:**

- `x$csplit` (line 58): a slot in the rpart fitted object that holds categorical split information; it is either a matrix (multiple categorical splits) or `NULL`/non-matrix (single or no categorical split). The check governs whether row indices are re-assigned sequentially.
- `ff$yval2` (line 36): a slot in the rpart frame; it is a matrix when the fitting method stores multi-column per-node values (e.g., class probabilities), or a plain vector otherwise. The check selects the appropriate `format()` call.

```r
# snip.rpart.R, line 58
if (is.matrix(x$csplit)) split[temp, 4L] <- 1L:nrow(x$csplit)

# snip.rpart.mouse.R, line 36
if (is.matrix(ff$yval2))
    cat(" (", format(ff$yval2[choose, ]), ")\n")
else
    cat(" (", format(ff$yval2[choose]), ")\n")
```

**Python Equivalent:**

```python
import numpy as np

# snip.rpart equivalent — csplit is a numpy array or None
if x_csplit is not None and isinstance(x_csplit, np.ndarray) and x_csplit.ndim == 2:
    split[temp, 3] = np.arange(1, x_csplit.shape[0] + 1)  # 0-based index column

# snip.rpart.mouse equivalent — yval2 is a numpy array or 1-D array
if isinstance(ff_yval2, np.ndarray) and ff_yval2.ndim == 2:
    print(f" ( {' '.join(str(v) for v in ff_yval2[choose, :])} )")
else:
    print(f" ( {ff_yval2[choose]} )")
```

**Explanation:** In R, `NULL` fields are common; in Python the equivalent is `None`. The index `split[temp, 4L]` uses 1-based column indexing in R; the Python equivalent is `split[temp, 3]` (0-based). `1L:nrow(x$csplit)` is `np.arange(1, x_csplit.shape[0] + 1)`. Row subset `ff$yval2[choose, ]` (all columns for one row) maps to `ff_yval2[choose, :]`.
