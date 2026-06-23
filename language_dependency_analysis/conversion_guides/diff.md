# Conversion Guide: `diff` (R to Python)

---

## 1. Overview of `diff` in R

`diff(x, lag = 1, differences = 1, ...)` computes lagged differences of a numeric vector (or matrix). For a plain numeric vector with the default arguments (`lag = 1`, `differences = 1`), it returns a vector of length `length(x) - 1` where each element is `x[i+1] - x[i]` — the successive first-order differences.

Key properties:
- **Input:** a numeric vector (or matrix) `x`.
- **Output:** a numeric vector of length `length(x) - lag * differences`, containing `x[i + lag] - x[i]` for each valid index `i`.
- The default `lag = 1` and `differences = 1` means simple pairwise consecutive subtraction.
- Applied to a two-element vector produced by `range()` (i.e. `c(min, max)`), `diff` returns a single scalar equal to `max - min`, the total span of the data.

---

## 2. Contextual Usage Analysis

All five CSV entries use `diff` with the default arguments (`lag = 1`, `differences = 1`). Two distinct patterns appear:

**Pattern A — Range span (scalar result):**
- `/groups/jli9/Yufei/python-rpart/rpart/R/plot.rpart.R`, function `plot.rpart`, lines 19 and 20.
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpartco.R`, function `rpartco`, line 43.

In all three of these calls the argument is `range(vector)`, which always returns a two-element vector `c(min, max)`. Applying `diff` to that two-element vector therefore produces a single scalar: `max - min`. The scalar is used immediately in an arithmetic expression to scale a margin offset or a fudge factor.

**Pattern B — Consecutive differences of an interval-boundary vector (vector result):**
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`, function `drate2`, line 55.
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`, function `rpart.exp`, line 103.

Here `itable` is a numeric vector of time-interval boundary points built as `c(0, dtimes[-length(dtimes)], max(time))`. It has length `k + 1` for some `k >= 1`. `diff(itable)` returns a vector of length `k` whose elements are the widths of the consecutive time intervals. These widths are used as multipliers in subsequent hazard-rate calculations and cumulative-hazard accumulation.

All arguments are plain 1-D numeric vectors; no matrices or higher-dimensional arrays are involved anywhere in these usages.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

R's `diff` is inherently a vectorized operation. `numpy.diff(a)` is the direct equivalent: it accepts any array-like input and returns an ndarray of consecutive differences with shape `(..., n-1)` along the last axis by default. This matches R's behaviour exactly for 1-D numeric vectors.

Reasons for preferring `numpy.diff` over alternatives:
- It is vectorized, matching R's semantics for both scalar-yielding and vector-yielding uses.
- It supports the same `n` (lag order) and `axis` parameters if higher-order differences or matrix inputs are ever needed.
- For Pattern A (`diff(range(x))`), `numpy.diff` on a two-element array returns a length-1 ndarray; a trailing `[0]` or `np.ptp` can extract the scalar, but in most NumPy arithmetic contexts the length-1 array is interchangeable with a scalar.
- `math` module functions are not suitable because they operate on scalars only and cannot handle vector inputs.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — `diff(range(vector))`: computing a range span

**Locations:**
- `plot.rpart.R` — function `plot.rpart`, lines 19–20
- `rpartco.R` — function `rpartco`, line 43

**Original R Context:**

```r
# xx and yy are numeric vectors of x- and y-coordinates of tree nodes.
# range() returns c(min, max); diff() on that returns max - min (a scalar).
temp1 <- range(xx) + diff(range(xx)) * c(-margin, margin)
temp2 <- range(yy) + diff(range(yy)) * c(-margin, margin)

# In rpartco.R:
# y is a numeric vector of node y-coordinates; diff(range(y)) is also max - min.
fudge <- minbranch * diff(range(y)) / max(depth)
```

- Input types: `xx`, `yy`, `y` are numeric vectors of arbitrary length.
- `range(v)` returns a two-element numeric vector.
- `diff(range(v))` returns a single numeric scalar (`max - min`).

**Python Equivalent:**

```python
import numpy as np

# xx, yy are 1-D numpy arrays (or lists) of node coordinates.
# np.ptp(a) returns a.max() - a.min(), which is identical to diff(range(a)) in R.
range_xx = np.array([xx.min(), xx.max()])         # equivalent to range(xx)
span_xx  = np.diff(range_xx)[0]                   # scalar: max - min
# or more concisely:
span_xx  = np.ptp(xx)                             # preferred one-liner

temp1 = np.array([xx.min(), xx.max()]) + span_xx * np.array([-margin, margin])
temp2 = np.array([yy.min(), yy.max()]) + np.ptp(yy) * np.array([-margin, margin])

# In rpartco equivalent:
fudge = minbranch * np.ptp(y) / depth.max()
```

**Explanation:**
- `np.diff(np.array([v.min(), v.max()]))[0]` replicates the two-step R idiom (`range` then `diff`) exactly.
- `np.ptp(v)` ("peak to peak") is the idiomatic NumPy shorthand for `max - min` and is the preferred single-call equivalent; it returns a scalar.
- The `[0]` index after `np.diff` on a two-element array extracts the scalar from the length-1 result array, which is necessary when a true Python scalar is required. In NumPy arithmetic expressions the length-1 array is usually sufficient without indexing.
- `c(-margin, margin)` in R becomes `np.array([-margin, margin])` in Python; NumPy broadcasts element-wise arithmetic automatically.

---

### 4.2 Pattern B — `diff(itable)`: consecutive differences of an interval-boundary vector

**Locations:**
- `rpart.exp.R` — function `drate2`, line 55
- `rpart.exp.R` — function `rpart.exp`, line 103

**Original R Context:**

```r
# itable is a numeric vector of length k+1 containing sorted time-interval
# boundary points: c(0, dtimes[-length(dtimes)], max(time)).
# diff(itable) returns a numeric vector of length k, each element being the
# width (length) of one time interval.

ilength <- diff(itable)       # in drate2: lengths of intervals
ngrp    <- length(ilength)    # number of intervals

# In rpart.exp (line 103):
cumhaz <- cumsum(c(0, rate * diff(itable)))
```

- Input type: `itable` is a numeric vector of length `k + 1` (`k >= 1`).
- Return type: numeric vector of length `k`, values `itable[i+1] - itable[i]`.

**Python Equivalent:**

```python
import numpy as np

# itable is a 1-D numpy array of sorted interval boundary points.
# np.diff(itable) computes consecutive differences, returning an array of
# length len(itable) - 1, exactly matching R's diff(itable).

ilength = np.diff(itable)          # array of interval widths, length k
ngrp    = len(ilength)             # number of intervals

# In rpart.exp equivalent (line 103):
cumhaz = np.cumsum(np.concatenate([[0.0], rate * np.diff(itable)]))
```

**Explanation:**
- `np.diff(itable)` is a direct, one-to-one replacement for R's `diff(itable)` when operating on a 1-D array with the default lag of 1. Both return an array/vector of length `n - 1` containing `a[i+1] - a[i]`.
- `np.cumsum(np.concatenate([[0.0], rate * np.diff(itable)]))` mirrors `cumsum(c(0, rate * diff(itable)))` in R: the prepended `0.0` ensures the cumulative hazard starts at zero, and `np.concatenate` is the NumPy equivalent of R's `c()` for joining arrays.
- No index-offset adjustment is needed: `np.diff` uses 0-based indexing internally, but the result has the same interpretation as R's 1-based output because both simply subtract adjacent elements in order.
- Import required: `import numpy as np`.
