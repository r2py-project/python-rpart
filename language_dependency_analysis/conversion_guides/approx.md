# Conversion Guide: `approx` in R

## 1. Overview of `approx` in R

`approx` is a base R function (from the `stats` package) that performs **linear or constant interpolation** on a set of known (x, y) data points, returning interpolated y-values at a new set of query x-values.

Key properties:

- **Signature:** `approx(x, y = NULL, xout, method = "linear", n = 50, yleft, yright, rule = 1, f = 0, ties = mean, na.rm = TRUE)`
- **Inputs:** `x` and `y` are numeric vectors of the same length defining the interpolation knots. `xout` (or the third positional argument) is the numeric vector of query points at which interpolated values are desired.
- **Return value:** A named list with two components, `$x` (the query points) and `$y` (the corresponding interpolated values). In practice only `$y` is used via the `$y` accessor.
- **Method:** Defaults to `"linear"`, which performs piecewise-linear interpolation between successive knots. `"constant"` produces a step function.
- **Extrapolation (`rule`):** When `rule = 1` (the default), query points outside the range of `x` return `NA`. When `rule = 2`, the nearest boundary value is returned instead.
- **Tie handling:** If `x` contains duplicate values, the `ties` argument determines how the corresponding `y` values are collapsed (default: `mean`).
- **Vectorized over `xout`:** A single `approx` call handles an entire vector of query points and returns a vector of the same length, making it the idiomatic R equivalent of a vectorized look-up / interpolation.

---

## 2. Contextual Usage Analysis

### Source location

- **File:** `rpart/R/rpart.exp.R`
- **Lines:** 104–105
- **Enclosing function:** `rpart.exp`

### Surrounding context

`rpart.exp` rescales a survival response so that the overall event rate equals 1.0 and local intervals appear Poisson-distributed. The rescaling is achieved by replacing raw time values with their **cumulative hazard** equivalents. The relevant block (lines 102–105) is:

```r
rate    <- drate2(n, ny, y, wt, itable)
cumhaz  <- cumsum(c(0, rate * diff(itable)))
newy    <- approx(itable, cumhaz, time)$y
if (ny == 3L) newy <- newy - approx(itable, cumhaz, y[, 1L])$y
```

Variable types and roles:

| Variable | Type | Description |
|---|---|---|
| `itable` | numeric vector, length `K+1` | Break-points of the time intervals (0, d1, d2, ..., max time). Serves as the x-knots. |
| `cumhaz` | numeric vector, length `K+1` | Cumulative hazard at each break-point. Serves as the y-knots. |
| `time` | numeric vector, length `n` | Observed follow-up time for each subject. Query points for line 104. |
| `y[, 1L]` | numeric vector, length `n` | Left-truncation (start) time for each subject (only present when `ny == 3`). Query points for line 105. |
| `newy` (line 104) | numeric vector, length `n` | Cumulative hazard evaluated at each subject's end time. |
| `newy` (line 105) | numeric vector, length `n` | Net cumulative hazard for the observed interval `[start, stop]`. |

**Recurring pattern:** Both calls use `approx` identically — linear interpolation of the step-wise cumulative hazard function at a vector of subject-level time points — and immediately extract only the `$y` component. The default `method = "linear"` and `rule = 1` apply in both cases (all query points are guaranteed to lie within the range of `itable` by construction).

---

## 3. Python Conversion Strategy

**Chosen library: `numpy` / `numpy.interp`**

R's `approx` with `method = "linear"` is directly equivalent to `numpy.interp(x, xp, fp)`. NumPy's `interp` is:

- **Vectorized:** accepts a 1-D array of query points and returns a 1-D array of interpolated values in a single call, matching R's behaviour exactly.
- **Zero-dependency:** part of NumPy's core, already a required dependency for any numerical Python project.
- **Extrapolation-compatible:** `numpy.interp` clamps to the boundary values (equivalent to R's `rule = 2`) by default. For the usage in `rpart.exp`, all query points fall within the knot range so this distinction does not matter in practice.

`scipy.interpolate.interp1d` is a valid alternative when more control over extrapolation or interpolation method is needed, but it introduces an extra `scipy` dependency and is more verbose for the straightforward linear case present here. `numpy.interp` is therefore preferred.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Linear interpolation of cumulative hazard at subject end-times

**Locations:** `rpart.exp.R` — `rpart.exp` (line 104)

**Original R context**

- `itable`: numeric vector of length `K+1` — interpolation x-knots (time break-points), strictly increasing.
- `cumhaz`: numeric vector of length `K+1` — interpolation y-knots (cumulative hazard at each break-point).
- `time`: numeric vector of length `n` — query points (subject follow-up end-times), all within `[min(itable), max(itable)]`.
- Return type: numeric vector of length `n` (the `$y` component of the list returned by `approx`).

```r
# General form
newy <- approx(itable, cumhaz, time)$y
```

**Python equivalent**

```python
import numpy as np

# itable : 1-D numpy array of shape (K+1,), strictly increasing
# cumhaz : 1-D numpy array of shape (K+1,)
# time   : 1-D numpy array of shape (n,)

newy = np.interp(time, itable, cumhaz)
# newy : 1-D numpy array of shape (n,)
```

**Explanation**

- `numpy.interp(x, xp, fp)` maps directly onto `approx(xp, fp, x)$y`:
  - `xp` corresponds to R's first argument (`itable`, the x-knots).
  - `fp` corresponds to R's second argument (`cumhaz`, the y-knots).
  - `x` corresponds to R's third argument (`time`, the query points).
- The argument order in NumPy (`x` first, then `xp`, then `fp`) is the reverse of R's positional convention (`x`-knots first, `y`-knots second, query last); take care not to swap them.
- `numpy.interp` uses piecewise-linear interpolation and clamps to boundary values outside the range, matching R's default `method = "linear"` behaviour for in-range queries.
- No `.y` accessor is needed; `numpy.interp` returns the interpolated values directly as a `numpy` array.

---

### 4.2 Linear interpolation of cumulative hazard at subject start-times (left-truncation adjustment)

**Locations:** `rpart.exp.R` — `rpart.exp` (line 105)

**Original R context**

- `itable`: numeric vector of length `K+1` — same x-knots as in 4.1.
- `cumhaz`: numeric vector of length `K+1` — same y-knots as in 4.1.
- `y[, 1L]`: numeric vector of length `n` — subject start (left-truncation) times; only present when `ny == 3` (start-stop interval format). Query points for the cumulative hazard at the start of each subject's observation window.
- Return type: numeric vector of length `n`.
- The result is subtracted from `newy` (computed in 4.1) to obtain the net cumulative hazard over each subject's observed interval `[start, stop]`.

```r
# General form (executed only when ny == 3L)
if (ny == 3L) newy <- newy - approx(itable, cumhaz, y[, 1L])$y
```

**Python equivalent**

```python
import numpy as np

# itable  : 1-D numpy array of shape (K+1,), strictly increasing
# cumhaz  : 1-D numpy array of shape (K+1,)
# y_start : 1-D numpy array of shape (n,)  — corresponds to y[:, 0] in Python
#            (R's y[, 1L] is the first column; Python uses 0-based column indexing)

if ny == 3:
    newy = newy - np.interp(y_start, itable, cumhaz)
```

**Explanation**

- The interpolation call itself is identical to 4.1; only the query array differs (`y[, 1L]` instead of `time`).
- R's column index `1L` (1-based, first column) translates to Python's column index `0` (0-based). If `y` is a 2-D NumPy array, the correct extraction is `y[:, 0]`.
- The subtraction `newy - approx(...)$y` is preserved as `newy - np.interp(...)` with standard NumPy element-wise arithmetic.
- Both `newy` arrays have shape `(n,)`, so the subtraction is a straightforward element-wise operation with no broadcasting needed.
