# Conversion Guide: `unclass` in R

---

## 1. Overview of `unclass` in R

`unclass()` is a base R function that returns a copy of its argument with its class attribute removed. It does not alter the underlying data or its storage structure; it solely strips the S3 class label so that subsequent operations bypass class-specific method dispatch and interact with the raw underlying representation.

**Typical inputs:** Any R object that carries a class attribute — most commonly factors, but also Date objects, model objects, or any S3-classed structure.

**Return value:** A copy of the input with the `class` attribute set to `NULL`. The object's actual data (e.g., integer codes for a factor, numeric values for a Date) is preserved exactly.

**Key behavioral details:**

- When applied to a **factor**, `unclass()` returns an integer vector of the factor's internal level codes (1-based), along with a `levels` attribute. The class label `"factor"` is removed, exposing the raw integer encoding.
- When applied to an **ordered factor** (e.g., the result of `cut()`), the same rule applies: the result is an integer vector whose values correspond to the ordered bin index.
- `unclass()` cannot be applied to environments or external pointers; those produce an error.
- It is semantically distinct from `as.integer()`: `unclass()` preserves all remaining attributes (such as `levels` and `labels`) while only removing the `class`; `as.integer()` drops all attributes and coerces the values.

---

## 2. Contextual Usage Analysis

The CSV identifies three call sites across two files, covering two distinct usage patterns.

### Pattern A — Strip class from a pre-existing factor response vector (`residuals.rpart.R`, line 23)

`y` is the response variable extracted from an `rpart` model object via `object$y`. When the model method is `"class"`, `y` is a **factor** whose levels are the class labels. `unclass(y)` converts this factor to its integer level codes (1-based), which are then used as column indices into a probability matrix:

```r
yhat <- yprob[cbind(seq(y), unclass(y))]
```

The result of `unclass(y)` is an integer vector of length `n` (number of observations). Each value selects the predicted class-probability column that corresponds to the true label of observation `i`. This is a standard R idiom for extracting the diagonal of a prediction matrix without an explicit loop.

### Pattern B — Strip class from the result of `cut()` (`rpart.exp.R`, lines 64 and 71)

Inside `drate2()`, `itable` is a numeric vector of interval boundaries. `cut(time, itable, include.lowest = TRUE)` returns an **ordered factor** whose levels are the interval labels (e.g., `"(0,1.2]"`, `"(1.2,3.5]"`, ...). `unclass()` converts this ordered factor to its **1-based integer bin index**, used immediately as a numeric index into `itable`:

```r
index  <- unclass(cut(time,  itable, include.lowest = TRUE))
itime  <- time - itable[index]

index2 <- unclass(cut(stime, itable, include.lowest = TRUE))
itime2 <- stime - itable[index2]
```

`index` and `index2` are integer vectors of the same length as `time` and `stime` respectively. They encode which interval each observation's follow-up end time (or start time) falls into. These indices are then used to look up the left boundary of that interval from `itable`, computing the time spent within the final (or initial) interval.

Both lines 64 and 71 are structurally identical; line 71 handles the left-truncated (delayed-entry) case where each subject also has a start time `stime`.

**Recurring patterns:**

- `unclass()` is always used to obtain an integer position that serves as a vector index.
- In Pattern A the factor already exists; in Pattern B the factor is created inline by `cut()`.
- In all cases the result is an integer vector, never a scalar.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy` (with `pandas` for `cut` equivalent).**

The rationale:

- All three call sites produce integer vectors (arrays), not scalars, so `numpy` array indexing is the natural target.
- `pandas.cut()` is the direct equivalent of R's `cut()`, returning a `Categorical` (analogous to a factor). Its `.codes` attribute exposes the 0-based integer bin indices, directly replacing `unclass(cut(...))`.
- For Pattern A, where `unclass()` is applied to a pre-existing factor-like object (a 1-based integer label array in the Python translation), no special function is needed — the integer array is already available, with index adjustment as described below.
- `numpy` integer array indexing (`arr[indices]`) then replaces R's vector indexing seamlessly.

**Critical indexing difference:** R factors and `cut()` produce **1-based** integer codes. Python's `pandas.cut(...).codes` produces **0-based** integer codes. All index arithmetic must be adjusted accordingly (see examples below).

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Using `unclass()` on a factor response vector

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 23.

**Original R Context:**

`y` is a factor with integer codes in `[1, nclass]`. `yprob` is a 2-D numeric matrix of shape `(n, nclass)`. The goal is to select, for each observation `i`, the predicted probability of its true class.

```r
# y: factor of length n, levels = ylevels (character vector of class names)
# yprob: numeric matrix, shape (n, nclass)
yhat <- yprob[cbind(seq(y), unclass(y))]
# Result: numeric vector of length n
```

`unclass(y)` yields a 1-based integer vector, used together with `seq(y)` (= `1:n`) to construct a 2-column row/column index matrix.

**Python Equivalent:**

```python
import numpy as np

# y_codes: 0-based integer array of shape (n,), analogous to unclass(y) - 1
# (In the Python translation, y is stored as a 0-based integer label array.)
# yprob: np.ndarray of shape (n, nclass)

n = len(y_codes)
row_idx = np.arange(n)          # equivalent to seq(y) - 1 (0-based rows)
col_idx = y_codes               # 0-based column indices (= unclass(y) - 1 in R)

yhat = yprob[row_idx, col_idx]  # advanced indexing: shape (n,)
```

**Explanation:**

- `unclass(y)` in R returns 1-based integer codes; in Python the equivalent label array is already 0-based, so no adjustment is needed if the labels were stored that way.
- If the Python labels are stored as 1-based (e.g., imported directly from R data), subtract 1: `col_idx = y_codes - 1`.
- `cbind(seq(y), unclass(y))` in R creates a two-column index matrix for simultaneous row+column selection. In numpy this is expressed as `arr[row_idx, col_idx]` (advanced/fancy indexing), which is both idiomatic and vectorized.
- No loop is required in either language.

---

### 4.2 Pattern B — Using `unclass(cut(...))` to obtain interval bin indices

**Locations:** `rpart.exp.R`, function `drate2`, lines 64 and 71.

**Original R Context:**

`itable` is a numeric vector of interval boundaries of length `m+1` (defining `m` intervals). `time` and `stime` are numeric vectors of length `n`. `cut()` assigns each value to an interval and returns an ordered factor; `unclass()` converts this to a 1-based integer bin index.

```r
# itable: numeric vector of break points, length m+1
# time:   numeric vector of length n (observation end times)
# stime:  numeric vector of length n (observation start times, ny == 3 case)

index  <- unclass(cut(time,  itable, include.lowest = TRUE))
itime  <- time - itable[index]          # time spent in the terminal interval

index2 <- unclass(cut(stime, itable, include.lowest = TRUE))
itime2 <- stime - itable[index2]        # time in the initial interval
```

`index` and `index2` are integer vectors of length `n`, each in `[1, m]`. They are used to look up `itable[index]` — the left boundary of the interval an observation falls in.

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# itable: np.ndarray of break points, shape (m+1,)
# time:   np.ndarray of shape (n,)
# stime:  np.ndarray of shape (n,)  [only when ny == 3]

# pandas.cut returns a Categorical; .codes gives 0-based integer bin indices
index  = pd.cut(time,  bins=itable, include_lowest=True).codes   # shape (n,), 0-based
itime  = time - itable[index]    # left boundary of each observation's terminal interval

# For the left-truncated (delayed entry) case:
index2 = pd.cut(stime, bins=itable, include_lowest=True).codes   # shape (n,), 0-based
itime2 = stime - itable[index2]
```

**Explanation:**

- `pd.cut(x, bins=itable, include_lowest=True)` is the direct equivalent of R's `cut(x, itable, include.lowest = TRUE)`. Both divide `x` into the intervals defined by `itable` and include the leftmost boundary in the first bin.
- `.codes` on the resulting `pandas.Categorical` returns a **0-based** integer array (dtype `int8` or `int16`). This replaces `unclass()` applied to the R factor.
- **Index offset:** R's `unclass(cut(...))` produces indices in `[1, m]`; `pd.cut(...).codes` produces indices in `[0, m-1]`. Because `itable[index]` in R accesses the 1-based left boundary, the Python equivalent `itable[index]` with 0-based `index` correctly accesses the same element since `itable` is a 0-based numpy array. No additional offset is needed for this specific lookup pattern.
- Values that fall outside `itable` would be coded as `-1` by `pd.cut` (the pandas sentinel for NA). The original R code does not guard against this either, relying on the construction of `itable` to guarantee all values are in range.
- `itable[index]` on a numpy array with a numpy integer array index is fully vectorized; no loop is needed.
- To convert the `.codes` array to a standard `int64` numpy array (avoiding int8 overflow risks in subsequent arithmetic), use `.codes.astype(np.int64)`.

**Complete self-contained example:**

```python
import numpy as np
import pandas as pd

# Example data matching the rpart.exp context
itable = np.array([0.0, 1.0, 2.5, 4.0, 6.0])   # 4 intervals
time   = np.array([0.8, 1.3, 2.5, 3.1, 5.9])    # n=5 end times

index = pd.cut(time, bins=itable, include_lowest=True).codes.astype(np.int64)
# index -> [0, 1, 2, 2, 3]  (0-based bin assignments)

itime = time - itable[index]
# itable[index] -> [0.0, 1.0, 2.5, 2.5, 4.0]
# itime         -> [0.8, 0.3, 0.0, 0.6, 1.9]
```
